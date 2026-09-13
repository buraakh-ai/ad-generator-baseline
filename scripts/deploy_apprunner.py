"""Deploys backend and frontend as two independent AWS App Runner
services, each with its own public HTTPS endpoint — no VPC/ALB/subnet
setup needed. Run this from a machine with Docker running and an
authenticated AWS CLI/boto3 session (`aws sts get-caller-identity` should
succeed before you run this).

What it does, in order:
  1. Creates the two ECR repositories if they don't exist.
  2. Builds + pushes backend and frontend images to ECR.
  3. Creates (if missing) the IAM role App Runner needs to pull from ECR.
  4. Creates (if missing) an auto-scaling configuration pinned to exactly
     one instance, and uses it for the BACKEND service only (see the
     "why one instance" note below) — the frontend uses App Runner's
     default auto-scaling.
  5. Creates or updates the backend App Runner service, waits for it to
     go RUNNING, and reads back its public URL.
  6. Creates or updates the frontend App Runner service with
     BACKEND_BASE_URL pointed at that backend URL, waits for RUNNING.
  7. Prints both public URLs.

Why the backend is pinned to one instance: /generate-image writes the ad
image to local disk, and a later /post-to-instagram|facebook|linkedin call
reads that same local path before re-uploading it to S3 (see
tools/instagram_tool.py). If App Runner ever scaled the backend to more
than one instance, a later request could land on a different instance
that never saw that file, and posting would fail with "Image file not
found". Pinning MinSize=MaxSize=1 avoids that; if you outgrow a single
instance later, the real fix is to make /generate-image upload straight
to S3 and have the post-* endpoints read from there instead of local
disk — tools/s3_tool.py already exists and does exactly that upload, it
just isn't wired into the /generate-image path yet.

Run with (from repo root, using the backend venv — it already has boto3):
    .venv/Scripts/python.exe -m scripts.deploy_apprunner --region us-east-2

Re-run any time after `git pull` + code changes: it rebuilds, re-pushes,
and updates both services in place (safe to run repeatedly).
"""
import argparse
import base64
import os
import subprocess
import sys
import time

import boto3

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ECR_ACCESS_ROLE_NAME = "AppRunnerECRAccessRole"
ECR_ACCESS_POLICY_ARN = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
SINGLE_INSTANCE_CONFIG_NAME = "ad-generator-single-instance"


def _load_env_file(path):
    env = {}
    if not os.path.exists(path):
        print(f"[deploy] warning: env file {path} not found — services will get no app env vars")
        return env
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def _run(cmd, **kwargs):
    print(f"[deploy] $ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, **kwargs)


def _check_aws_auth(region):
    try:
        identity = boto3.client("sts", region_name=region).get_caller_identity()
        print(f"[deploy] authenticated as {identity['Arn']} (account {identity['Account']})")
        return identity["Account"]
    except Exception as e:
        print(f"[deploy] AWS auth check failed: {e}")
        print("[deploy] reauthenticate (e.g. `aws sso login` or set IAM keys) and try again.")
        sys.exit(1)


def _ensure_ecr_repo(ecr, name):
    try:
        resp = ecr.create_repository(repositoryName=name)
        print(f"[deploy] created ECR repo {name}")
        return resp["repository"]["repositoryUri"]
    except ecr.exceptions.RepositoryAlreadyExistsException:
        resp = ecr.describe_repositories(repositoryNames=[name])
        return resp["repositories"][0]["repositoryUri"]


def _docker_login_ecr(ecr, region, account_id):
    auth = ecr.get_authorization_token()["authorizationData"][0]
    user, password = base64.b64decode(auth["authorizationToken"]).decode().split(":", 1)
    registry = auth["proxyEndpoint"].replace("https://", "")
    print(f"[deploy] docker login {registry}")
    subprocess.run(
        ["docker", "login", "--username", user, "--password-stdin", registry],
        input=password.encode(), check=True,
    )


def _build_and_push(dockerfile, image_uri):
    _run(["docker", "build", "-f", dockerfile, "-t", image_uri, "."], cwd=_ROOT_DIR)
    _run(["docker", "push", image_uri])


def _ensure_ecr_access_role(iam):
    trust_policy = """{
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Principal": {"Service": "build.apprunner.amazonaws.com"}, "Action": "sts:AssumeRole"}]
    }"""
    try:
        role = iam.create_role(RoleName=ECR_ACCESS_ROLE_NAME, AssumeRolePolicyDocument=trust_policy)["Role"]
        print(f"[deploy] created IAM role {ECR_ACCESS_ROLE_NAME}")
    except iam.exceptions.EntityAlreadyExistsException:
        role = iam.get_role(RoleName=ECR_ACCESS_ROLE_NAME)["Role"]
    iam.attach_role_policy(RoleName=ECR_ACCESS_ROLE_NAME, PolicyArn=ECR_ACCESS_POLICY_ARN)
    return role["Arn"]


def _ensure_single_instance_autoscaling(apprunner):
    resp = apprunner.list_auto_scaling_configurations(AutoScalingConfigurationName=SINGLE_INSTANCE_CONFIG_NAME)
    for cfg in resp.get("AutoScalingConfigurationSummaryList", []):
        if cfg["Status"] == "ACTIVE":
            return cfg["AutoScalingConfigurationArn"]
    created = apprunner.create_auto_scaling_configuration(
        AutoScalingConfigurationName=SINGLE_INSTANCE_CONFIG_NAME, MinSize=1, MaxSize=1, MaxConcurrency=100,
    )
    return created["AutoScalingConfiguration"]["AutoScalingConfigurationArn"]


def _find_service_arn(apprunner, name):
    next_token = None
    while True:
        kwargs = {"NextToken": next_token} if next_token else {}
        resp = apprunner.list_services(**kwargs)
        for svc in resp["ServiceSummaryList"]:
            if svc["ServiceName"] == name:
                return svc["ServiceArn"]
        next_token = resp.get("NextToken")
        if not next_token:
            return None


def _create_or_update_service(apprunner, name, image_uri, port, env_vars, access_role_arn,
                               autoscaling_arn=None, health_check_path="/"):
    source_configuration = {
        "ImageRepository": {
            "ImageIdentifier": image_uri,
            "ImageRepositoryType": "ECR",
            "ImageConfiguration": {"Port": str(port), "RuntimeEnvironmentVariables": env_vars},
        },
        "AuthenticationConfiguration": {"AccessRoleArn": access_role_arn},
        "AutoDeploymentsEnabled": True,
    }
    health_check_configuration = {
        "Protocol": "HTTP", "Path": health_check_path,
        "Interval": 10, "Timeout": 5, "HealthyThreshold": 1, "UnhealthyThreshold": 5,
    }

    existing_arn = _find_service_arn(apprunner, name)
    if existing_arn:
        print(f"[deploy] {name}: existing service found, updating...")
        kwargs = dict(ServiceArn=existing_arn, SourceConfiguration=source_configuration,
                      HealthCheckConfiguration=health_check_configuration)
        if autoscaling_arn:
            kwargs["AutoScalingConfigurationArn"] = autoscaling_arn
        apprunner.update_service(**kwargs)
        return existing_arn

    print(f"[deploy] {name}: no existing service, creating...")
    kwargs = dict(
        ServiceName=name,
        SourceConfiguration=source_configuration,
        InstanceConfiguration={"Cpu": "1024", "Memory": "2048"},
        HealthCheckConfiguration=health_check_configuration,
    )
    if autoscaling_arn:
        kwargs["AutoScalingConfigurationArn"] = autoscaling_arn
    resp = apprunner.create_service(**kwargs)
    return resp["Service"]["ServiceArn"]


def _wait_for_running(apprunner, service_arn, timeout=900):
    start = time.time()
    while time.time() - start < timeout:
        svc = apprunner.describe_service(ServiceArn=service_arn)["Service"]
        print(f"[deploy] {svc['ServiceName']}: {svc['Status']}")
        if svc["Status"] == "RUNNING":
            return svc
        if svc["Status"] in ("CREATE_FAILED", "DELETE_FAILED"):
            raise RuntimeError(f"{svc['ServiceName']} entered {svc['Status']} — check the App Runner console for logs")
        time.sleep(15)
    raise TimeoutError(f"Timed out waiting for {service_arn} to become RUNNING")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-2"))
    parser.add_argument("--env-file", default=os.path.join(_ROOT_DIR, ".env"))
    parser.add_argument("--backend-service-name", default="ad-generator-backend")
    parser.add_argument("--frontend-service-name", default="ad-generator-frontend")
    parser.add_argument("--ecr-backend-repo", default="ad-generator-backend")
    parser.add_argument("--ecr-frontend-repo", default="ad-generator-frontend")
    parser.add_argument("--skip-build", action="store_true", help="Skip docker build/push; just (re)create/update the App Runner services from the image tags already in ECR.")
    args = parser.parse_args()

    account_id = _check_aws_auth(args.region)

    ecr = boto3.client("ecr", region_name=args.region)
    iam = boto3.client("iam", region_name=args.region)
    apprunner = boto3.client("apprunner", region_name=args.region)

    backend_repo_uri = _ensure_ecr_repo(ecr, args.ecr_backend_repo)
    frontend_repo_uri = _ensure_ecr_repo(ecr, args.ecr_frontend_repo)
    backend_image = f"{backend_repo_uri}:latest"
    frontend_image = f"{frontend_repo_uri}:latest"

    if not args.skip_build:
        _docker_login_ecr(ecr, args.region, account_id)
        _build_and_push("Dockerfile.backend", backend_image)
        _build_and_push("Dockerfile.frontend", frontend_image)
    else:
        print("[deploy] --skip-build set: assuming images are already pushed to ECR")

    access_role_arn = _ensure_ecr_access_role(iam)
    single_instance_arn = _ensure_single_instance_autoscaling(apprunner)

    app_env = _load_env_file(args.env_file)
    app_env.pop("BACKEND_BASE_URL", None)  # backend doesn't need this; set below for the frontend only

    backend_arn = _create_or_update_service(
        apprunner, args.backend_service_name, backend_image, port=8000,
        env_vars=app_env, access_role_arn=access_role_arn, autoscaling_arn=single_instance_arn,
    )
    backend_service = _wait_for_running(apprunner, backend_arn)
    backend_url = f"https://{backend_service['ServiceUrl']}"
    print(f"[deploy] backend live at {backend_url}")

    frontend_arn = _create_or_update_service(
        apprunner, args.frontend_service_name, frontend_image, port=8501,
        env_vars={"BACKEND_BASE_URL": backend_url}, access_role_arn=access_role_arn,
    )
    frontend_service = _wait_for_running(apprunner, frontend_arn)
    frontend_url = f"https://{frontend_service['ServiceUrl']}"
    print(f"[deploy] frontend live at {frontend_url}")

    print("\n[deploy] done.")
    print(f"  Frontend (open this in your browser): {frontend_url}")
    print(f"  Backend API (callable on its own):     {backend_url}   (try: curl {backend_url}/)")


if __name__ == "__main__":
    main()
