"""Image-prompt building + PIL compositing (text overlay, logo chip,
gradient scrim). The compositing side is pure deterministic logic, ported
from the original image_generator.py. The prompt-building side asks
gpt-4o-mini for a campaign-specific background-scene description
(_build_ai_scene, via core/model_router.py) and falls back to the
deterministic keyword-matched scene library below (_template_scene) if that
call fails for any reason — same "try the LLM, fall back to a plain-logic
default" pattern used throughout skills/. The wrapper *template* around the
scene — the fixed "photorealistic, no people, no text, full bleed" quality
constraints — lives in prompts/image_prompt.yaml so it's editable without
touching code; the scene/style lookup tables below are data, not prompts,
so they stay in Python. Used by agents/image_agent.py."""
import os
import random
import textwrap
from io import BytesIO

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from core.prompt_loader import load_prompt, render

TARGET_W, TARGET_H = 1080, 1350

# ---------------------------------------------------------------------------
# Scene / style library
# ---------------------------------------------------------------------------

INDUSTRY_SCENES = {
    "sports": ["empty professional sports stadium, bright sunny day, vivid green pitch, blue sky, wide angle",
               "stadium exterior golden hour, warm amber light on concrete and steel",
               "sports arena at night, floodlights blazing over empty pitch, atmospheric mist"],
    "basketball": ["empty NBA hardwood court, bright overhead arena lights, glossy floor",
                   "basketball arena, bright white lighting, empty bleachers, crisp court lines"],
    "soccer": ["empty football stadium, lush green pitch, bright sunny day, blue sky",
               "soccer stadium at golden hour, warm light raking across the grass",
               "football pitch at night under floodlights, vivid green, atmospheric haze"],
    "football": ["NFL stadium sunny day, green turf with white yard lines, blue sky, wide angle",
                 "football stadium at golden hour, warm amber light on the field"],
    "volleyball": ["beach volleyball court, sunny day, white sand, blue sky, net in focus",
                   "indoor volleyball arena, bright overhead lighting, empty court"],
    "tennis": ["tennis court bright sunny day, vivid color, crisp white lines, blue sky",
               "clay tennis court warm afternoon sun, long shadows, rich terracotta"],
    "running": ["athletics track bright clear day, vivid red lanes, blue sky",
                "city marathon route at sunrise, golden light on empty streets"],
    "swimming": ["Olympic pool, crystal clear blue water, clean white lane ropes, bright light",
                 "outdoor pool sunny day, sparkling blue water, vivid blue sky"],
    "golf": ["golf course fairway bright sunny day, lush green grass, blue sky",
             "golf course golden hour, warm light across rolling green fairways"],
    "technology": ["sleek modern glass office building exterior, bright blue sky reflection",
                   "bright open-plan modern office, floor-to-ceiling windows, natural daylight",
                   "glass office tower golden hour, warm light on facade, city below"],
    "fashion": ["minimalist fashion studio flooded with natural daylight, clean white surfaces",
                "bright sunlit empty retail space, polished floors, minimal displays"],
    "food": ["fresh colorful ingredients bright wooden surface, natural window light",
             "modern restaurant interior warm lighting, empty elegant tables"],
    "finance": ["financial district skyline bright clear day, glass towers reflecting blue sky",
                "city skyline golden hour, warm amber light on glass and steel towers",
                "financial district at night, towers of light reflecting on water",
                "modern glass office lobby, natural light, clean architectural lines"],
    "health": ["bright clean wellness studio, natural light through windows, wooden floor",
               "peaceful outdoor nature scene, green landscape, soft morning light"],
    "real_estate": ["modern architectural exterior bright sunny day, clean lines, blue sky",
                    "luxury interior natural light, floor-to-ceiling windows, minimal"],
    "travel": ["sweeping landscape vista bright clear day, vivid natural colors, wide horizon",
               "tropical coastline aerial, turquoise water and white sand, bright sun"],
    "beauty": ["close-up flower petals, soft natural backlight, pastel tones, delicate",
               "minimal flat-lay bright white surface, soft natural shadows, editorial"],
    "automotive": ["empty open highway horizon bright sunny day, dramatic perspective",
                   "winding mountain road clear day, vivid landscape, adventure"],
    "music": ["concert venue interior bright day, empty floor, high ceilings, natural light",
              "empty music stage bright white stage lights, clean dramatic"],
    "default": ["city skyline bright clear day, glass towers reflecting blue sky",
                "sweeping landscape golden hour, warm light, atmospheric depth",
                "modern architectural interior natural daylight, clean minimal",
                "dramatic seascape bright day, vivid blue water, clear sky",
                "city skyline at night, towers of light reflecting on water"],
}

SPORT_SCENE_MAP = {k: INDUSTRY_SCENES[k] for k in
                    ["basketball", "soccer", "football", "volleyball", "tennis", "running", "swimming", "golf"]}
GENERIC_SPORT = INDUSTRY_SCENES["sports"]

INDUSTRY_KEYWORDS = {
    "technology": ["tech", "software", "app", "digital", "saas", "cloud", "ai ", "data", "cyber", "developer"],
    "fashion": ["fashion", "clothing", "apparel", "wear", "style", "outfit", "streetwear", "luxury"],
    "food": ["food", "restaurant", "cafe", "coffee", "drink", "beverage", "meal", "cuisine", "bakery"],
    "finance": ["finance", "bank", "invest", "trading", "insurance", "fintech", "wealth", "fund",
                "capital", "tax", "accounting", "cfo", "bookkeeping", "financial"],
    "health": ["health", "wellness", "fitness", "gym", "medical", "supplement", "yoga", "nutrition"],
    "real_estate": ["real estate", "property", "homes", "housing", "realty", "architecture"],
    "travel": ["travel", "airline", "hotel", "tourism", "vacation", "holiday", "destination"],
    "beauty": ["beauty", "skincare", "cosmetics", "makeup", "hair", "spa", "grooming"],
    "automotive": ["car", "auto", "vehicle", "motor", "drive", "electric vehicle", "truck", "suv"],
    "music": ["music", "artist", "album", "concert", "streaming", "record", "sound"],
}


def _template_scenes(*texts):
    """Deterministic fallback: returns the keyword-matched list of
    candidate scenes to random.choice() from, instead of asking the LLM."""
    combined = " ".join(t.lower() for t in texts if t)
    for sport, scenes in SPORT_SCENE_MAP.items():
        if sport in combined:
            return scenes * 4
    sport_hints = ["match", "tournament", "championship", "league", "athlete", "stadium", "arena", "playoffs"]
    if any(h in combined for h in sport_hints):
        return GENERIC_SPORT * 3
    for industry, kws in INDUSTRY_KEYWORDS.items():
        if any(k in combined for k in kws):
            return INDUSTRY_SCENES[industry]
    return INDUSTRY_SCENES["default"]


def _tone_to_style(brand_tone):
    t = (brand_tone or "").lower()
    if any(w in t for w in ["luxury", "premium", "elegant", "sophisticated"]):
        return "luxury editorial photography, minimal composition, high-end magazine aesthetic"
    if any(w in t for w in ["bold", "energetic", "dynamic", "powerful", "athletic"]):
        return "high-energy commercial photography, bold high-contrast, vivid saturated colors"
    if any(w in t for w in ["friendly", "warm", "approachable", "casual", "authentic"]):
        return "warm lifestyle photography, natural authentic light, inviting soft warm tones"
    if any(w in t for w in ["professional", "corporate", "trusted", "authoritative", "expert"]):
        return "clean professional commercial photography, sharp authoritative composition"
    if any(w in t for w in ["fun", "playful", "youthful", "vibrant", "creative"]):
        return "vibrant lifestyle photography, bright vivid colors, energetic bold composition"
    if any(w in t for w in ["natural", "organic", "sustainable", "eco", "fresh"]):
        return "bright natural lifestyle photography, soft diffused light, clean organic tones"
    return "professional commercial photography, clean polished composition, Instagram-ready"


# ---------------------------------------------------------------------------
# Prompt builder — wrapper template lives in prompts/image_prompt.yaml,
# the {scene} slot is AI-generated (prompts/image_scene.yaml) with a
# deterministic fallback if that call fails.
# ---------------------------------------------------------------------------

def _build_ai_scene(company_name, instagram_copy, event_context, company_details, image_headline):
    """Asks gpt-4o-mini for a campaign-specific background-scene
    description. Raises on any failure — build_image_prompt() catches it
    and falls back to _template_scenes()."""
    from core.agno_models import build_agno_agent
    from core.model_router import generate_text
    from skills.event_selection_skill import GENERIC_EVENT_FALLBACK

    # The vague "no real event found" fallback isn't something to
    # visualize literally — treat it the same as no event at all, so the
    # model grounds the scene in the company/brand instead of drifting
    # toward generic "current events" imagery (which tends to read as a
    # bland corporate/news scene, not an actual creative choice).
    has_real_event = bool(event_context and event_context.strip() and event_context.strip() != GENERIC_EVENT_FALLBACK)
    event_for_prompt = event_context if has_real_event else "(none)"

    system_prompt, user_prompt = render(
        "image_scene",
        company_name=company_name,
        what_they_do=company_details.get("what_they_do", ""),
        brand_tone=company_details.get("brand_tone", "professional"),
        event_context=event_for_prompt,
        image_headline=image_headline,
        instagram_copy=instagram_copy,
    )
    try:
        agent = build_agno_agent(complexity="low", instructions=system_prompt)
        result = agent.run(user_prompt)
        raw = getattr(result, "content", None) or str(result)
    except Exception as e:
        print(f"[image] Agno path unavailable ({e}) — using model_router fallback")
        raw = generate_text(user_prompt, system_prompt, complexity="low")
    scene = raw.strip().strip('"').strip("'").rstrip(". ").strip()
    if not scene:
        raise ValueError("empty scene description")
    return scene


def build_image_prompt(company_name, instagram_copy, event_context, company_details, config, image_headline=""):
    if config.get("override_prompt", "").strip():
        return config["override_prompt"].strip()

    services = company_details.get("services", "")
    brand_tone = company_details.get("brand_tone", "professional")
    style = _tone_to_style(brand_tone)

    try:
        scene = _build_ai_scene(company_name, instagram_copy, event_context, company_details, image_headline)
        print(f"[image] AI-generated scene: {scene[:160]}...")
    except Exception as e:
        print(f"[image] AI scene generation failed ({e}) — using template fallback")
        scene = random.choice(_template_scenes(event_context, instagram_copy, services, company_name))

    template = load_prompt("image_prompt")
    core = template.get("core", "").strip().format(scene=scene, style=style)

    prefix = config.get("prompt_prefix", "").strip()
    suffix = config.get("prompt_suffix", "").strip()
    return " ".join(p for p in [prefix, core, suffix] if p)


# ---------------------------------------------------------------------------
# Compositing helpers
# ---------------------------------------------------------------------------

def _fill_to_target(img, tw=TARGET_W, th=TARGET_H):
    img = img.convert("RGB")
    iw, ih = img.size
    scale = max(tw / iw, th / ih)
    if scale != 1.0:
        img = img.resize((max(int(iw * scale), tw), max(int(ih * scale), th)), Image.LANCZOS)
    iw, ih = img.size
    left = (iw - tw) // 2
    top = (ih - th) // 2
    return img.crop((left, top, left + tw, top + th))


def _font(name, size):
    for f in [name, name.lower(), "arial.ttf", "LiberationSans-Regular.ttf", "DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(f, size)
        except Exception:
            continue
    return ImageFont.load_default()


def fetch_logo(logo_url):
    if not logo_url or not logo_url.startswith("http"):
        return None
    try:
        r = requests.get(logo_url, timeout=10)
        if r.status_code == 200:
            return Image.open(BytesIO(r.content)).convert("RGBA")
    except Exception as e:
        print(f"[logo] {e}")
    return None


def _frosted_chip(canvas_rgba, logo_thumb, cx, cy, cw, ch, pad=12, radius=12):
    base = canvas_rgba.convert("RGB")
    region = base.crop((cx, cy, cx + cw, cy + ch))
    frosted = region.filter(ImageFilter.GaussianBlur(16))
    bright = sum(frosted.convert("L").getdata()) / (cw * ch)
    if bright < 100:
        tint = (255, 255, 255, 170)
    elif bright < 140:
        tint = (240, 240, 240, 130)
    elif bright > 180:
        tint = (10, 10, 10, 100)
    else:
        tint = (20, 20, 20, 80)
    tl = Image.new("RGBA", frosted.size, tint)
    fr = Image.alpha_composite(frosted.convert("RGBA"), tl)
    out = canvas_rgba.copy()
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=radius, fill=255)
    out.paste(fr, (cx, cy), mask)
    out.paste(logo_thumb, (cx + pad, cy + pad), logo_thumb)
    return out


def _circle_crop(logo_img, size):
    c = logo_img.copy().convert("RGBA")
    c.thumbnail((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    lw, lh = c.size
    out.paste(c, ((size - lw) // 2, (size - lh) // 2), c)
    out.putalpha(mask)
    return out


def _text_size(draw, text, font):
    try:
        bb = draw.textbbox((0, 0), text, font=font)
        return bb[2] - bb[0], bb[3] - bb[1]
    except AttributeError:
        return draw.textsize(text, font=font)


def _stroke_text(draw, pos, text, font, fill=(255, 255, 255), stroke_color=(0, 0, 0), stroke=2):
    x, y = pos
    for ox in range(-stroke, stroke + 1):
        for oy in range(-stroke, stroke + 1):
            if ox != 0 or oy != 0:
                draw.text((x + ox, y + oy), text, font=font, fill=stroke_color)
    draw.text((x, y), text, font=font, fill=fill)


# ---------------------------------------------------------------------------
# Display (on-image UI) version
# ---------------------------------------------------------------------------

def build_display_image(base_image, company_name, image_headline, instagram_copy, logo=None):
    img = _fill_to_target(base_image)
    W, H = img.size

    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    fh = int(H * 0.48)
    fs = H - fh
    for i in range(fh):
        a = int((i / fh) ** 1.5 * 175)
        gd.line([(0, fs + i), (W, fs + i)], fill=(0, 0, 0, a))
    ui_h = 185
    ui_y = H - ui_h
    for i in range(ui_h):
        a = min(170 + int((i / ui_h) * 65), 235)
        gd.line([(0, ui_y + i), (W, ui_y + i)], fill=(0, 0, 0, a))
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, grad)

    if logo:
        lt = logo.copy()
        lt.thumbnail((78, 78), Image.LANCZOS)
        pad = 12
        cw = lt.width + pad * 2
        ch = lt.height + pad * 2
        cx = W - cw - 26
        cy = 26
        img = _frosted_chip(img, lt, cx, cy, cw, ch, pad=pad)

    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)

    btn_h = 66
    btn_y = ui_y - btn_h
    draw.rectangle([0, btn_y, W, btn_y + btn_h], fill=(15, 15, 15))
    draw.line([(0, btn_y), (W, btn_y)], fill=(55, 55, 55), width=1)
    font_btn = _font("arialbd.ttf", 27)
    btn_label = "Learn More"
    btw, bth = _text_size(draw, btn_label, font_btn)
    bx = (W - btw) // 2 - 12
    by = btn_y + (btn_h - bth) // 2
    draw.text((bx, by), btn_label, font=font_btn, fill=(255, 255, 255))
    ax = bx + btw + 18
    ay = btn_y + btn_h // 2
    draw.polygon([(ax, ay - 9), (ax + 14, ay), (ax, ay + 9)], fill=(170, 170, 170))

    tx = 46
    fn = _font("arialbd.ttf", 36)
    fb = _font("arial.ttf", 28)
    ny = btn_y - 130
    _stroke_text(draw, (tx, ny), company_name.upper(), fn, fill=(255, 255, 255), stroke_color=(0, 0, 0), stroke=2)
    if image_headline and image_headline.strip():
        hy = ny + 55
        for line in textwrap.wrap(image_headline.strip(), width=36)[:2]:
            _stroke_text(draw, (tx, hy), line, fb, fill=(238, 238, 238), stroke_color=(0, 0, 0), stroke=1)
            hy += 42

    pad_ui = 18
    pic_size = 54
    row_y = ui_y + 14
    if logo:
        circle = _circle_crop(logo, pic_size)
        bg_circ = Image.new("RGBA", (pic_size, pic_size), (60, 60, 60, 255))
        bg_circ.paste(circle, (0, 0), circle)
        img.paste(bg_circ.convert("RGB"), (pad_ui, row_y))
    else:
        draw.ellipse([pad_ui, row_y, pad_ui + pic_size, row_y + pic_size], fill=(80, 80, 80))

    font_handle = _font("arialbd.ttf", 28)
    name_x = pad_ui + pic_size + 14
    name_y = row_y + (pic_size // 2) - 16
    name_w, _ = _text_size(draw, company_name, font_handle)
    draw.text((name_x, name_y), company_name, font=font_handle, fill=(255, 255, 255))

    font_follow = _font("arialbd.ttf", 22)
    follow_txt = "Follow"
    ftw, fth = _text_size(draw, follow_txt, font_follow)
    fb_w = ftw + 28
    fb_h = 36
    fb_x = name_x + name_w + 16
    fb_y = row_y + (pic_size // 2) - (fb_h // 2)
    draw.rounded_rectangle([fb_x, fb_y, fb_x + fb_w, fb_y + fb_h], radius=6, outline=(220, 220, 220), width=2)
    draw.text((fb_x + (fb_w - ftw) // 2, fb_y + (fb_h - fth) // 2), follow_txt, font=font_follow, fill=(220, 220, 220))

    font_cap = _font("arial.ttf", 23)
    words = [w for w in (instagram_copy or "").split() if not w.startswith("#")]
    preview = " ".join(words)
    if len(preview) > 85:
        preview = preview[:82] + "..."
    elif not preview.endswith("..."):
        preview += " ..."
    cap_y = row_y + pic_size + 10
    draw.text((pad_ui, cap_y), preview, font=font_cap, fill=(200, 200, 200))

    font_ad = _font("arial.ttf", 21)
    aw, _ = _text_size(draw, "Ad", font_ad)
    draw.text((W - aw - pad_ui, H - 30), "Ad", font=font_ad, fill=(165, 165, 165))
    return img


# ---------------------------------------------------------------------------
# Clean version (no on-image UI chrome)
# ---------------------------------------------------------------------------

def build_clean_image(base_image, company_name, image_headline, logo=None):
    img = _fill_to_target(base_image)
    W, H = img.size
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    fh = int(H * 0.42)
    fs = H - fh
    for i in range(fh):
        a = int((i / fh) ** 1.5 * 170)
        gd.line([(0, fs + i), (W, fs + i)], fill=(0, 0, 0, a))
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, grad)

    if logo:
        lt = logo.copy()
        lt.thumbnail((78, 78), Image.LANCZOS)
        pad = 12
        cw = lt.width + pad * 2
        ch = lt.height + pad * 2
        cx = W - cw - 26
        cy = 26
        img = _frosted_chip(img, lt, cx, cy, cw, ch, pad=pad)

    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)
    tx = 46
    fn = _font("arialbd.ttf", 36)
    fb = _font("arial.ttf", 28)
    ny = int(H * 0.72)
    _stroke_text(draw, (tx, ny), company_name.upper(), fn, fill=(255, 255, 255), stroke_color=(0, 0, 0), stroke=2)
    if image_headline and image_headline.strip():
        hy = ny + 55
        for line in textwrap.wrap(image_headline.strip(), width=36)[:2]:
            _stroke_text(draw, (tx, hy), line, fb, fill=(238, 238, 238), stroke_color=(0, 0, 0), stroke=1)
            hy += 42
    return img


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def composite_ad_image(base_image, company_name, image_headline, instagram_copy, logo_url=None, static_dir="static"):
    """Builds both the display (on-image UI) and clean versions, saves them
    under static_dir, and returns (display_path, clean_path)."""
    logo = fetch_logo(logo_url)

    print("[image] building display image (on-image UI)...")
    display = build_display_image(base_image, company_name, image_headline, instagram_copy, logo)

    print("[image] building clean version...")
    clean = build_clean_image(base_image, company_name, image_headline, logo)

    os.makedirs(static_dir, exist_ok=True)
    display_path = os.path.join(static_dir, "generated_ad.jpg")
    clean_path = os.path.join(static_dir, "generated_ad_clean.jpg")

    display.save(display_path, "JPEG", quality=95)
    clean.save(clean_path, "JPEG", quality=95)

    print(f"[image] saved display -> {display_path}")
    print(f"[image] saved clean   -> {clean_path}")

    return display_path.replace(os.sep, "/"), clean_path.replace(os.sep, "/")
