"""Imagens OpenGraph (1200x630) geradas no tema do BSBR.

Usa Pillow com fontes embutidas do Pillow (não depende de fontes do sistema).
- player: avatar + nome + rank BR + PP + colunas ACC/TECH/SPEED
- map: cover + nome + mapper + stars + BPM
"""

from __future__ import annotations

import io
import textwrap

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
BG = (9, 9, 11)  # zinc-950
SECONDARY = (59, 130, 246)  # blue-500
ACCENT = (239, 68, 68)  # red-500
SUCCESS = (34, 197, 94)
TEXT = (244, 244, 245)  # zinc-100
MUTED = (161, 161, 170)  # zinc-400
DANGER = (239, 68, 68)

# Fontes: Pillow FreeTypeFont com paths padrão das wheels
def _fetch_image(url: str) -> Image.Image | None:
    """Baixa a imagem com httpx (User-Agent de browser).

    urllib.request recebe 403 do CDN do BeatSaver; httpx com User-Agent
    normal passa. Retorna a imagem RGB ou None em qualquer falha.
    """
    try:
        import httpx

        resp = httpx.get(
            url,
            timeout=10,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (BSBR-OG)"},
        )
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception:
        return None


def _font(size: int, bold: bool = False):
    import os

    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if bold else ""),
        "C:/Windows/Fonts/arial%s.ttf" % ("bd" if bold else ""),
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _round_mask(size: tuple[int, int], radius: int) -> Image.Image:
    from PIL import ImageDraw as _D

    mask = Image.new("L", size, 0)
    _D.Draw(mask).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return mask


def _draw_player(payload: dict) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # cantos com gradiente (simula o radial do site)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for i in range(80):
        alpha = max(0, 26 - i)
        od.ellipse([-200 - i * 2, -160 - i, -200 - i * 2 + 700, -160 - i + 700], fill=(239, 68, 68, alpha))
        od.ellipse([W - 480 + i, H - 300 + i, W - 480 + i + 620, H - 300 + i + 620], fill=(59, 130, 246, alpha))
    img.paste(overlay, (0, 0), overlay)

    # avatar (arredondado) — fallback para inicial
    avatar = None
    if payload.get("avatar_url"):
        avatar = _fetch_image(payload["avatar_url"])
    avatar_size = 170
    if avatar:
        avatar = avatar.resize((avatar_size, avatar_size), Image.LANCZOS)
        mask = _round_mask((avatar_size, avatar_size), 24)
    else:
        avatar = Image.new("RGB", (avatar_size, avatar_size), (39, 39, 42))
        ImageDraw.Draw(avatar).text(
            (avatar_size // 2, avatar_size // 2),
            (payload.get("name") or "?")[:1].upper(),
            fill=TEXT,
            font=_font(72, bold=True),
            anchor="mm",
        )
        mask = _round_mask((avatar_size, avatar_size), 24)
    img.paste(avatar, (70, 70), mask)

    f_name = _font(54, bold=True)
    f_sub = _font(30)
    f_big = _font(64, bold=True)
    f_small = _font(26)
    f_label = _font(20, bold=True)

    name = (payload.get("name") or "Jogador")[:34]
    d.text((70 + avatar_size + 40, 78), name, font=f_name, fill=TEXT)

    rank = payload.get("rank")
    country = payload.get("country") or ""
    sub = "Ranking BSBR"
    if country:
        sub += f"  ·  {country}"
    d.text((70 + avatar_size + 40, 150), sub, font=f_sub, fill=MUTED)

    # bloco central: PP grande + rótulo (destaque principal do card)
    pp = payload.get("pp_total") or 0
    pp_text = f"{pp:,.0f}"
    pp_x = 70 + avatar_size + 40
    d.text((pp_x, 218), pp_text, font=_font(76, bold=True), fill=SECONDARY)
    d.text((pp_x, 306), "PP  ·  pontuação de performance", font=f_label, fill=MUTED)

    # rank no canto superior direito (chip)
    if rank is not None:
        r_x = W - 430
        d.text((r_x, 92), f"#{rank}", font=_font(76, bold=True), fill=TEXT)
        d.text((r_x + 10, 186), "BRASIL", font=_font(22, bold=True), fill=ACCENT)

    # barras ACC/TECH/SPEED
    comps = [
        ("ACC", payload.get("pp_acc") or 0, SECONDARY),
        ("TECH", payload.get("pp_tech") or 0, ACCENT),
        ("SPEED", payload.get("pp_speed") or 0, SUCCESS),
    ]
    total = sum(c[1] for c in comps) or 1
    bar_y = 430
    bar_w = (W - 140) // 3
    for i, (label, val, color) in enumerate(comps):
        x = 70 + i * (bar_w + 20)
        d.rectangle([x, bar_y, x + bar_w, bar_y + 18], fill=(39, 39, 42))
        d.rectangle([x, bar_y, x + bar_w * min(val / max(total, 1), 1), bar_y + 18], fill=color)
        d.text((x, bar_y + 34), label, font=f_label, fill=color)
        d.text((x + bar_w - 10, bar_y + 34), f"{val:,.0f}", font=f_small, fill=TEXT, anchor="ra")

    d.text((70, H - 64), "bsbr.pro", font=_font(26, bold=True), fill=MUTED)
    return img


def _draw_map(payload: dict) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # cover à esquerda (cobre ~60% da largura)
    cover = None
    if payload.get("cover_url"):
        cover = _fetch_image(payload["cover_url"])
    if cover:
        cover = cover.resize((W * 3 // 5, H), Image.LANCZOS)
        img.paste(cover, (0, 0))
    else:
        for i in range(80):
            alpha = max(0, 24 - i)
            ImageDraw.Draw(img).ellipse([-160 - i * 2, -120 - i, -160 - i * 2 + 640, -120 - i + 640], fill=(239, 68, 68, alpha))

    # faixa escura para o texto (overlay RGBA com alpha real — em RGB o 4º
    # valor do fill não é alpha e pintaria o cover todo de preto)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([0, 0, 300, H], fill=(9, 9, 11, 235))
    od.rectangle([300, 0, W, H], fill=(9, 9, 11, 175))
    od.rectangle([296, 0, 300, H], fill=(239, 68, 68, 255))  # filete accent
    img.paste(overlay, (0, 0), overlay)
    d = ImageDraw.Draw(img)

    name = payload.get("name") or "Mapa"
    # remove sufixos de feat/versão japonesa que a fonte DejaVu não cobre (vira tofu)
    import re

    clean_name = re.split(r"\s*(?:~|/)\s*", name)[0].strip()[:48]
    lines = textwrap.wrap(clean_name, width=24)[:3]
    for i, line in enumerate(lines):
        d.text((70, 70 + 54 * i), line, font=_font(44, bold=True), fill=TEXT)

    mapper = payload.get("mapper") or ""
    d.text((70, 300), mapper[:38], font=_font(28), fill=MUTED)

    stars = payload.get("total_stars")
    if stars is not None:
        d.text((70, 370), f"{stars:.2f}", font=_font(96, bold=True), fill=SECONDARY)
        d.text((70, 490), "DIFICULDADE (STARS)", font=_font(22, bold=True), fill=MUTED)

    bpm = payload.get("bpm")
    if bpm:
        d.text((70, 540), f"{bpm:.0f} BPM", font=_font(28, bold=True), fill=TEXT)

    d.text((70, H - 64), "bsbr.pro", font=_font(26, bold=True), fill=MUTED)
    return img


def render(payload: dict) -> bytes:
    img = _draw_map(payload) if payload.get("kind") == "map" else _draw_player(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
