"""
BSBR OpenGraph Generator V2
============================

Imagens OpenGraph (1200x630) com visual moderno para o BSBR.

Mantém a mesma interface pública:

    render(payload) -> bytes

Tipos suportados:
- player
- map

O arquivo também pode ser executado diretamente para gerar imagens
de teste usando dados fictícios.
"""

from __future__ import annotations

import io
import math
import os
import re
import textwrap
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont


# ============================================================
# CONFIGURAÇÃO
# ============================================================

W, H = 1200, 630

# Background
BG = (9, 9, 12)
BG_CARD = (20, 20, 27)
BG_CARD_2 = (28, 28, 36)

# Cores principais BSBR
BLUE = (59, 130, 246)
BLUE_LIGHT = (96, 165, 250)

RED = (239, 68, 68)
RED_LIGHT = (248, 113, 113)

GREEN = (34, 197, 94)
PURPLE = (168, 85, 247)
YELLOW = (250, 204, 21)

TEXT = (250, 250, 250)
TEXT_SECONDARY = (161, 161, 170)
TEXT_DIM = (113, 113, 122)

WHITE = (255, 255, 255)


# ============================================================
# FONTES
# ============================================================

@lru_cache(maxsize=64)
def _font(size: int, bold: bool = False):
    """
    Carrega uma fonte TrueType de forma compatível com:
    - Windows
    - Ubuntu
    - Debian
    - Docker
    - Alpine (caso fontes sejam instaladas)

    Também suporta uma fonte embutida/local no projeto.
    """

    base_dir = os.path.dirname(os.path.abspath(__file__))

    # Permite definir manualmente via variável de ambiente:
    #
    # BSBR_FONT_REGULAR=/app/fonts/DejaVuSans.ttf
    # BSBR_FONT_BOLD=/app/fonts/DejaVuSans-Bold.ttf
    #
    env_font = (
        os.getenv("BSBR_FONT_BOLD")
        if bold
        else os.getenv("BSBR_FONT_REGULAR")
    )

    candidates = []

    if env_font:
        candidates.append(env_font)

    # ========================================================
    # FONTES EMBUTIDAS NO PROJETO (RECOMENDADO)
    # ========================================================

    if bold:
        candidates.extend([
            os.path.join(base_dir, "fonts", "DejaVuSans-Bold.ttf"),
            os.path.join(base_dir, "fonts", "NotoSans-Bold.ttf"),
            os.path.join(base_dir, "fonts", "Inter-Bold.ttf"),
        ])
    else:
        candidates.extend([
            os.path.join(base_dir, "fonts", "DejaVuSans.ttf"),
            os.path.join(base_dir, "fonts", "NotoSans-Regular.ttf"),
            os.path.join(base_dir, "fonts", "Inter-Regular.ttf"),
        ])

    # ========================================================
    # WINDOWS
    # ========================================================

    if bold:
        candidates.extend([
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
        ])
    else:
        candidates.extend([
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibri.ttf",
        ])

    # ========================================================
    # UBUNTU / DEBIAN
    # ========================================================

    if bold:
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansDisplay-Bold.ttf",
        ])
    else:
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansDisplay-Regular.ttf",
        ])

    # ========================================================
    # ALPINE
    # ========================================================

    if bold:
        candidates.extend([
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        ])
    else:
        candidates.extend([
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        ])

    # ========================================================
    # macOS
    # ========================================================

    if bold:
        candidates.extend([
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        ])
    else:
        candidates.extend([
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ])

    # ========================================================
    # TENTA CARREGAR
    # ========================================================

    for path in candidates:

        if not path:
            continue

        if os.path.isfile(path):
            try:
                return ImageFont.truetype(
                    path,
                    size=size,
                )
            except Exception:
                continue

    raise RuntimeError(
        "Nenhuma fonte TrueType (.ttf) foi encontrada.\n\n"
        "Instale fonts-dejavu-core no sistema ou inclua as fontes "
        "na pasta ./fonts do projeto.\n\n"
        f"Diretório atual: {base_dir}"
    )


# ============================================================
# DOWNLOAD DE IMAGENS
# ============================================================

def _fetch_image(url: str) -> Image.Image | None:
    """
    Baixa uma imagem remota.

    Retorna None caso aconteça qualquer erro.
    """

    if not url:
        return None

    try:
        import httpx

        response = httpx.get(
            url,
            timeout=10,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (BSBR-OG/2.0)"
            },
        )

        response.raise_for_status()

        return Image.open(
            io.BytesIO(response.content)
        ).convert("RGB")

    except Exception:
        return None


# ============================================================
# UTILITÁRIOS DE IMAGEM
# ============================================================

def _rounded_mask(
    size: tuple[int, int],
    radius: int,
) -> Image.Image:
    """Cria uma máscara arredondada."""

    mask = Image.new("L", size, 0)

    draw = ImageDraw.Draw(mask)

    draw.rounded_rectangle(
        [0, 0, size[0] - 1, size[1] - 1],
        radius=radius,
        fill=255,
    )

    return mask


def _paste_rounded(
    base: Image.Image,
    image: Image.Image,
    position: tuple[int, int],
    size: tuple[int, int],
    radius: int,
):
    """
    Redimensiona e cola uma imagem com cantos arredondados.
    """

    image = image.resize(size, Image.LANCZOS)

    mask = _rounded_mask(size, radius)

    base.paste(
        image,
        position,
        mask,
    )


def _cover_crop(
    image: Image.Image,
    size: tuple[int, int],
) -> Image.Image:
    """
    Faz crop estilo CSS object-fit: cover.
    """

    target_w, target_h = size

    source_w, source_h = image.size

    source_ratio = source_w / source_h
    target_ratio = target_w / target_h

    if source_ratio > target_ratio:

        # Imagem muito larga
        new_h = target_h
        new_w = int(source_ratio * new_h)

    else:

        # Imagem muito alta
        new_w = target_w
        new_h = int(new_w / source_ratio)

    resized = image.resize(
        (new_w, new_h),
        Image.LANCZOS,
    )

    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2

    return resized.crop(
        (
            left,
            top,
            left + target_w,
            top + target_h,
        )
    )


def _add_gradient(
    image: Image.Image,
    start_color: tuple[int, int, int],
    end_color: tuple[int, int, int],
    horizontal: bool = False,
):
    """
    Aplica um gradiente simples.
    """

    draw = ImageDraw.Draw(image)

    length = image.width if horizontal else image.height

    for i in range(length):

        t = i / max(length - 1, 1)

        color = tuple(
            int(start_color[c] * (1 - t) + end_color[c] * t)
            for c in range(3)
        )

        if horizontal:

            draw.line(
                [(i, 0), (i, image.height)],
                fill=color,
            )

        else:

            draw.line(
                [(0, i), (image.width, i)],
                fill=color,
            )


def _add_glow(
    image: Image.Image,
    center: tuple[int, int],
    radius: int,
    color: tuple[int, int, int],
    alpha: int = 100,
):
    """
    Cria um glow circular suave.
    """

    glow = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(glow)

    x, y = center

    draw.ellipse(
        (
            x - radius,
            y - radius,
            x + radius,
            y + radius,
        ),
        fill=(
            color[0],
            color[1],
            color[2],
            alpha,
        ),
    )

    blur_radius = max(20, radius // 2)

    glow = glow.filter(
        ImageFilter.GaussianBlur(blur_radius)
    )

    image.paste(
        glow,
        (0, 0),
        glow,
    )


def _draw_shadow(
    image: Image.Image,
    box: tuple[int, int, int, int],
    radius: int = 25,
    alpha: int = 100,
):
    """
    Desenha uma sombra suave atrás de um card.
    """

    shadow = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(shadow)

    x1, y1, x2, y2 = box

    offset = 10

    draw.rounded_rectangle(
        (
            x1,
            y1 + offset,
            x2,
            y2 + offset,
        ),
        radius=radius,
        fill=(0, 0, 0, alpha),
    )

    shadow = shadow.filter(
        ImageFilter.GaussianBlur(15)
    )

    image.paste(
        shadow,
        (0, 0),
        shadow,
    )


def _draw_glass_card(
    image: Image.Image,
    box: tuple[int, int, int, int],
    radius: int = 24,
    fill: tuple[int, int, int, int] = (24, 24, 32, 220),
    border: tuple[int, int, int, int] = (255, 255, 255, 18),
):
    """
    Card estilo glassmorphism.
    """

    _draw_shadow(
        image,
        box,
        radius,
        alpha=80,
    )

    overlay = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(overlay)

    draw.rounded_rectangle(
        box,
        radius=radius,
        fill=fill,
        outline=border,
        width=1,
    )

    image.paste(
        overlay,
        (0, 0),
        overlay,
    )


def _text_bbox(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
):
    """Retorna o bounding box do texto."""

    return draw.textbbox(
        (0, 0),
        text,
        font=font,
    )


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    initial_size: int,
    min_size: int = 20,
    bold: bool = True,
):
    """
    Reduz automaticamente a fonte até caber.
    """

    size = initial_size

    while size >= min_size:

        font = _font(size, bold=bold)

        bbox = _text_bbox(
            draw,
            text,
            font,
        )

        width = bbox[2] - bbox[0]

        if width <= max_width:
            return font

        size -= 2

    return _font(min_size, bold=bold)


# ============================================================
# BACKGROUND PRINCIPAL
# ============================================================

def _create_background() -> Image.Image:
    """
    Background padrão da identidade BSBR.
    """

    image = Image.new(
        "RGB",
        (W, H),
        BG,
    )

    # Gradiente vertical extremamente discreto
    gradient = Image.new(
        "RGB",
        (W, H),
        BG,
    )

    _add_gradient(
        gradient,
        (9, 9, 12),
        (15, 15, 22),
    )

    image.paste(gradient)

    # Glows
    _add_glow(
        image,
        (120, 40),
        250,
        RED,
        75,
    )

    _add_glow(
        image,
        (W - 120, H - 80),
        280,
        BLUE,
        75,
    )

    # Linhas decorativas diagonais
    decoration = Image.new(
        "RGBA",
        (W, H),
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(decoration)

    for x in range(-400, W + 400, 150):

        draw.line(
            (
                x,
                H,
                x + 450,
                0,
            ),
            fill=(255, 255, 255, 6),
            width=2,
        )

    image.paste(
        decoration,
        (0, 0),
        decoration,
    )

    return image


# ============================================================
# BRANDING
# ============================================================

def _draw_brand(
    image: Image.Image,
    x: int,
    y: int,
    small: bool = False,
):
    """
    Logo textual simples do BSBR.
    """

    draw = ImageDraw.Draw(image)

    if small:

        size = 22
        dot_size = 8

    else:

        size = 28
        dot_size = 10

    # Indicador visual
    draw.ellipse(
        (
            x,
            y + 8,
            x + dot_size,
            y + 8 + dot_size,
        ),
        fill=RED,
    )

    draw.text(
        (
            x + dot_size + 10,
            y,
        ),
        "BSBR",
        font=_font(size, bold=True),
        fill=TEXT,
    )

    draw.text(
        (
            x + dot_size + 10 + (size * 2.8),
            y + 4,
        ),
        ".PRO",
        font=_font(max(14, size // 2), bold=True),
        fill=TEXT_DIM,
    )


# ============================================================
# COMPONENTE: BADGE
# ============================================================

def _draw_badge(
    image: Image.Image,
    x: int,
    y: int,
    text: str,
    color: tuple[int, int, int],
):
    """
    Badge arredondado.
    """

    draw = ImageDraw.Draw(image)

    font = _font(18, bold=True)

    bbox = draw.textbbox(
        (0, 0),
        text,
        font=font,
    )

    width = bbox[2] - bbox[0]

    padding_x = 16
    padding_y = 10

    box = (
        x,
        y,
        x + width + padding_x * 2,
        y + 38,
    )

    overlay = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
    )

    od = ImageDraw.Draw(overlay)

    od.rounded_rectangle(
        box,
        radius=19,
        fill=(
            color[0],
            color[1],
            color[2],
            45,
        ),
        outline=(
            color[0],
            color[1],
            color[2],
            100,
        ),
    )

    image.paste(
        overlay,
        (0, 0),
        overlay,
    )

    draw = ImageDraw.Draw(image)

    draw.text(
        (
            x + padding_x,
            y + 7,
        ),
        text,
        font=font,
        fill=color,
    )


# ============================================================
# COMPONENTE: STAT CARD
# ============================================================

def _draw_stat_card(
    image: Image.Image,
    box: tuple[int, int, int, int],
    label: str,
    value: float,
    color: tuple[int, int, int],
    suffix: str = "PP",
):
    """
    Card individual de estatística.
    """

    x1, y1, x2, y2 = box

    _draw_glass_card(
        image,
        box,
        radius=20,
        fill=(22, 22, 30, 235),
        border=(255, 255, 255, 15),
    )

    draw = ImageDraw.Draw(image)

    # Barra superior colorida
    overlay = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
    )

    od = ImageDraw.Draw(overlay)

    od.rounded_rectangle(
        (
            x1 + 1,
            y1 + 1,
            x2 - 1,
            y1 + 6,
        ),
        radius=4,
        fill=(
            color[0],
            color[1],
            color[2],
            220,
        ),
    )

    image.paste(
        overlay,
        (0, 0),
        overlay,
    )

    draw = ImageDraw.Draw(image)

    draw.text(
        (
            x1 + 22,
            y1 + 24,
        ),
        label,
        font=_font(17, bold=True),
        fill=color,
    )

    value_text = f"{value:,.0f}"

    draw.text(
        (
            x1 + 22,
            y1 + 52,
        ),
        value_text,
        font=_font(34, bold=True),
        fill=TEXT,
    )

    draw.text(
        (
            x1 + 22,
            y1 + 95,
        ),
        suffix,
        font=_font(15, bold=True),
        fill=TEXT_DIM,
    )


# ============================================================
# PLAYER
# ============================================================

def _draw_player(payload: dict) -> Image.Image:

    image = _create_background()

    draw = ImageDraw.Draw(image)

    # --------------------------------------------------------
    # BRAND
    # --------------------------------------------------------

    _draw_brand(
        image,
        55,
        36,
        small=True,
    )

    _draw_badge(
        image,
        W - 190,
        34,
        "PLAYER",
        BLUE_LIGHT,
    )

    # --------------------------------------------------------
    # AVATAR
    # --------------------------------------------------------

    avatar_size = 190

    avatar_x = 65
    avatar_y = 120

    avatar = None

    if payload.get("avatar_url"):
        avatar = _fetch_image(
            payload["avatar_url"]
        )

    # Shadow / glow do avatar
    _add_glow(
        image,
        (
            avatar_x + avatar_size // 2,
            avatar_y + avatar_size // 2,
        ),
        130,
        BLUE,
        55,
    )

    # Fundo do avatar
    _draw_glass_card(
        image,
        (
            avatar_x - 8,
            avatar_y - 8,
            avatar_x + avatar_size + 8,
            avatar_y + avatar_size + 8,
        ),
        radius=30,
        fill=(20, 20, 28, 220),
        border=(96, 165, 250, 80),
    )

    if avatar:

        avatar = _cover_crop(
            avatar,
            (
                avatar_size,
                avatar_size,
            ),
        )

        _paste_rounded(
            image,
            avatar,
            (
                avatar_x,
                avatar_y,
            ),
            (
                avatar_size,
                avatar_size,
            ),
            radius=24,
        )

    else:

        fallback = Image.new(
            "RGB",
            (
                avatar_size,
                avatar_size,
            ),
            (39, 39, 48),
        )

        fd = ImageDraw.Draw(fallback)

        initial = (
            payload.get("name")
            or "?"
        )[0].upper()

        fd.text(
            (
                avatar_size // 2,
                avatar_size // 2,
            ),
            initial,
            font=_font(90, bold=True),
            fill=TEXT,
            anchor="mm",
        )

        _paste_rounded(
            image,
            fallback,
            (
                avatar_x,
                avatar_y,
            ),
            (
                avatar_size,
                avatar_size,
            ),
            radius=24,
        )

    # --------------------------------------------------------
    # INFORMAÇÕES DO JOGADOR
    # --------------------------------------------------------

    info_x = 305

    name = (
        payload.get("name")
        or "Jogador"
    )[:40]

    name_font = _fit_text(
        draw,
        name,
        max_width=500,
        initial_size=56,
        min_size=30,
        bold=True,
    )

    draw.text(
        (
            info_x,
            120,
        ),
        name,
        font=name_font,
        fill=TEXT,
    )

    country = payload.get("country") or "Brasil"

    draw.text(
        (
            info_x,
            190,
        ),
        f"Ranking BSBR  ·  {country}",
        font=_font(24),
        fill=TEXT_SECONDARY,
    )

    # --------------------------------------------------------
    # PP PRINCIPAL
    # --------------------------------------------------------

    pp = payload.get("pp_total") or 0

    draw.text(
        (
            info_x,
            250,
        ),
        f"{pp:,.0f}",
        font=_font(72, bold=True),
        fill=WHITE,
    )

    draw.text(
        (
            info_x,
            335,
        ),
        "PERFORMANCE POINTS",
        font=_font(18, bold=True),
        fill=BLUE_LIGHT,
    )

    # --------------------------------------------------------
    # RANK
    # --------------------------------------------------------

    rank = payload.get("rank")

    if rank is not None:

        rank_x1 = 870
        rank_y1 = 120

        rank_box = (
            rank_x1,
            rank_y1,
            1135,
            325,
        )

        _draw_glass_card(
            image,
            rank_box,
            radius=26,
            fill=(24, 24, 32, 230),
            border=(239, 68, 68, 35),
        )

        # Linha lateral
        overlay = Image.new(
            "RGBA",
            image.size,
            (0, 0, 0, 0),
        )

        od = ImageDraw.Draw(overlay)

        od.rounded_rectangle(
            (
                rank_x1,
                rank_y1,
                rank_x1 + 7,
                325,
            ),
            radius=4,
            fill=(
                RED[0],
                RED[1],
                RED[2],
                230,
            ),
        )

        image.paste(
            overlay,
            (0, 0),
            overlay,
        )

        draw = ImageDraw.Draw(image)

        draw.text(
            (
                rank_x1 + 28,
                rank_y1 + 24,
            ),
            "RANK BRASIL",
            font=_font(17, bold=True),
            fill=TEXT_DIM,
        )

        draw.text(
            (
                rank_x1 + 28,
                rank_y1 + 58,
            ),
            f"#{rank}",
            font=_font(82, bold=True),
            fill=TEXT,
        )

        draw.text(
            (
                rank_x1 + 30,
                rank_y1 + 158,
            ),
            "BSBR RANKING",
            font=_font(16, bold=True),
            fill=RED_LIGHT,
        )

    # --------------------------------------------------------
    # STAT CARDS
    # --------------------------------------------------------

    stats_y = 415

    margin = 65
    gap = 18

    card_width = (
        W
        - margin * 2
        - gap * 2
    ) // 3

    card_height = 150

    stats = [
        (
            "ACC",
            payload.get("pp_acc") or 0,
            BLUE,
        ),
        (
            "TECH",
            payload.get("pp_tech") or 0,
            PURPLE,
        ),
        (
            "SPEED",
            payload.get("pp_speed") or 0,
            GREEN,
        ),
    ]

    for i, (
        label,
        value,
        color,
    ) in enumerate(stats):

        x = margin + i * (
            card_width + gap
        )

        _draw_stat_card(
            image,
            (
                x,
                stats_y,
                x + card_width,
                stats_y + card_height,
            ),
            label,
            value,
            color,
        )

    # --------------------------------------------------------
    # FOOTER
    # --------------------------------------------------------

    draw = ImageDraw.Draw(image)

    draw.text(
        (
            65,
            H - 38,
        ),
        "BEAT SABER BRASIL RANKING",
        font=_font(15, bold=True),
        fill=TEXT_DIM,
    )

    draw.text(
        (
            W - 65,
            H - 38,
        ),
        "bsbr.pro",
        font=_font(18, bold=True),
        fill=TEXT_SECONDARY,
        anchor="ra",
    )

    return image


# ============================================================
# MAP
# ============================================================

def _create_map_background(
    cover: Image.Image | None,
) -> Image.Image:
    """
    Cria o background do mapa.

    Se existir cover:
    - usa o próprio cover
    - faz crop
    - blur
    - escurece

    Caso contrário:
    - usa o background padrão.
    """

    if cover is None:
        return _create_background()

    background = _cover_crop(
        cover,
        (W, H),
    )

    background = background.filter(
        ImageFilter.GaussianBlur(28)
    )

    # Escurece o background
    dark = Image.new(
        "RGBA",
        (W, H),
        (5, 5, 8, 195),
    )

    background = background.convert("RGBA")

    background.alpha_composite(dark)

    background = background.convert("RGB")

    # Adiciona glows BSBR
    _add_glow(
        background,
        (100, 100),
        200,
        RED,
        50,
    )

    _add_glow(
        background,
        (W - 150, H - 100),
        250,
        BLUE,
        55,
    )

    return background


def _draw_map(payload: dict) -> Image.Image:

    # --------------------------------------------------------
    # COVER
    # --------------------------------------------------------

    cover = None

    if payload.get("cover_url"):

        cover = _fetch_image(
            payload["cover_url"]
        )

    image = _create_map_background(
        cover
    )

    draw = ImageDraw.Draw(image)

    # --------------------------------------------------------
    # BRAND
    # --------------------------------------------------------

    _draw_brand(
        image,
        55,
        36,
        small=True,
    )

    _draw_badge(
        image,
        W - 165,
        34,
        "MAP",
        RED_LIGHT,
    )

    # --------------------------------------------------------
    # COVER CARD
    # --------------------------------------------------------

    cover_x = 65
    cover_y = 105

    cover_w = 410
    cover_h = 420

    # Glow atrás do cover
    _add_glow(
        image,
        (
            cover_x + cover_w // 2,
            cover_y + cover_h // 2,
        ),
        210,
        RED,
        40,
    )

    _draw_glass_card(
        image,
        (
            cover_x - 8,
            cover_y - 8,
            cover_x + cover_w + 8,
            cover_y + cover_h + 8,
        ),
        radius=30,
        fill=(15, 15, 20, 210),
        border=(255, 255, 255, 30),
    )

    if cover:

        cropped_cover = _cover_crop(
            cover,
            (
                cover_w,
                cover_h,
            ),
        )

        _paste_rounded(
            image,
            cropped_cover,
            (
                cover_x,
                cover_y,
            ),
            (
                cover_w,
                cover_h,
            ),
            radius=24,
        )

    else:

        fallback = Image.new(
            "RGB",
            (
                cover_w,
                cover_h,
            ),
            BG_CARD,
        )

        # Gradiente fictício
        fd = ImageDraw.Draw(fallback)

        for y in range(cover_h):

            t = y / cover_h

            r = int(RED[0] * (1 - t) + BLUE[0] * t)
            g = int(RED[1] * (1 - t) + BLUE[1] * t)
            b = int(RED[2] * (1 - t) + BLUE[2] * t)

            fd.line(
                (
                    0,
                    y,
                    cover_w,
                    y,
                ),
                fill=(r // 3, g // 3, b // 3),
            )

        fd.text(
            (
                cover_w // 2,
                cover_h // 2,
            ),
            "BSBR",
            font=_font(64, bold=True),
            fill=TEXT,
            anchor="mm",
        )

        _paste_rounded(
            image,
            fallback,
            (
                cover_x,
                cover_y,
            ),
            (
                cover_w,
                cover_h,
            ),
            radius=24,
        )

    # --------------------------------------------------------
    # INFORMAÇÕES DO MAPA
    # --------------------------------------------------------

    info_x = 540

    name = (
        payload.get("name")
        or "Mapa desconhecido"
    )

    # Mantém a lógica de limpar versões/feat
    clean_name = re.split(
        r"\s*(?:~|/)\s*",
        name,
    )[0].strip()

    clean_name = clean_name[:60]

    # Quebra o nome em linhas
    lines = textwrap.wrap(
        clean_name,
        width=30,
    )[:2]

    current_y = 110

    for idx, line in enumerate(lines):

        fs = 48 if len(lines) > 1 else 52
        font = _fit_text(
            draw,
            line,
            max_width=590,
            initial_size=fs,
            min_size=28,
            bold=True,
        )

        draw.text(
            (
                info_x,
                current_y,
            ),
            line,
            font=font,
            fill=TEXT,
        )

        current_y += 56

    # --------------------------------------------------------
    # MAPPER (com espaçamento extra do título)
    # --------------------------------------------------------

    mapper = (
        payload.get("mapper")
        or "Mapper desconhecido"
    )[:45]

    mapper_y = current_y + 14

    draw.text(
        (
            info_x,
            mapper_y,
        ),
        "MAPPED BY",
        font=_font(16, bold=True),
        fill=TEXT_DIM,
    )

    draw.text(
        (
            info_x,
            mapper_y + 28,
        ),
        mapper,
        font=_font(24, bold=True),
        fill=TEXT_SECONDARY,
    )

    # --------------------------------------------------------
    # STARS
    # --------------------------------------------------------

    stars = payload.get("total_stars")

    if stars is None:
        stars = 0

    stars_y = 340

    _draw_glass_card(
        image,
        (
            info_x,
            stars_y,
            830,
            500,
        ),
        radius=24,
        fill=(22, 22, 30, 230),
        border=(59, 130, 246, 40),
    )

    draw = ImageDraw.Draw(image)

    draw.text(
        (
            info_x + 28,
            stars_y + 25,
        ),
        "DIFFICULTY",
        font=_font(16, bold=True),
        fill=TEXT_DIM,
    )

    draw.text(
        (
            info_x + 28,
            stars_y + 58,
        ),
        f"{stars:.2f}",
        font=_font(60, bold=True),
        fill=BLUE_LIGHT,
    )

    draw.text(
        (
            info_x + 28,
            stars_y + 123,
        ),
        "STARS",
        font=_font(17, bold=True),
        fill=BLUE,
    )

    # --------------------------------------------------------
    # BPM
    # --------------------------------------------------------

    bpm = payload.get("bpm") or 0

    _draw_glass_card(
        image,
        (
            850,
            stars_y,
            1135,
            500,
        ),
        radius=24,
        fill=(22, 22, 30, 230),
        border=(239, 68, 68, 40),
    )

    draw = ImageDraw.Draw(image)

    draw.text(
        (
            878,
            stars_y + 25,
        ),
        "TEMPO",
        font=_font(16, bold=True),
        fill=TEXT_DIM,
    )

    draw.text(
        (
            878,
            stars_y + 58,
        ),
        f"{bpm:.0f}",
        font=_font(60, bold=True),
        fill=RED_LIGHT,
    )

    draw.text(
        (
            878,
            stars_y + 123,
        ),
        "BPM",
        font=_font(17, bold=True),
        fill=RED,
    )

    # --------------------------------------------------------
    # FOOTER
    # --------------------------------------------------------

    draw.text(
        (
            65,
            H - 38,
        ),
        "BEAT SABER BRASIL RANKING",
        font=_font(15, bold=True),
        fill=TEXT_DIM,
    )

    draw.text(
        (
            W - 65,
            H - 38,
        ),
        "bsbr.pro",
        font=_font(18, bold=True),
        fill=TEXT_SECONDARY,
        anchor="ra",
    )

    return image


# ============================================================
# API PÚBLICA
# ============================================================

def render(payload: dict) -> bytes:
    """
    Renderiza uma imagem OpenGraph.

    Payload exemplo:

    PLAYER:
    {
        "kind": "player",
        "name": "RedstoneAlmeida",
        "country": "Brazil",
        "rank": 1,
        "pp_total": 12500,
        "pp_acc": 4200,
        "pp_tech": 3900,
        "pp_speed": 4400,
        "avatar_url": "https://..."
    }

    MAP:
    {
        "kind": "map",
        "name": "Nome do mapa",
        "mapper": "Nome do mapper",
        "total_stars": 9.42,
        "bpm": 174,
        "cover_url": "https://..."
    }
    """

    kind = payload.get(
        "kind",
        "player",
    )

    if kind == "map":
        image = _draw_map(payload)
    else:
        image = _draw_player(payload)

    buffer = io.BytesIO()

    image.save(
        buffer,
        format="PNG",
        optimize=True,
    )

    return buffer.getvalue()


# ============================================================
# TESTES COM DADOS FICTÍCIOS
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # PLAYER FICTÍCIO
    # --------------------------------------------------------

    fake_player = {
        "kind": "player",

        "name": "RedstoneAlmeida",

        "country": "Brazil",

        "rank": 7,

        "pp_total": 12_847.62,

        "pp_acc": 4_320.0,

        "pp_tech": 3_985.0,

        "pp_speed": 4_542.0,

        # Deixe None para testar o fallback
        "avatar_url": None,
    }

    # --------------------------------------------------------
    # MAP FICTÍCIO
    # --------------------------------------------------------

    fake_map = {
        "kind": "map",

        "name": "Neon Through The Digital Horizon",

        "mapper": "BSBR Community Mapper",

        "total_stars": 9.42,

        "bpm": 174,

        # Deixe None para testar o fallback
        "cover_url": None,
    }

    # --------------------------------------------------------
    # GERA OS ARQUIVOS
    # --------------------------------------------------------

    with open(
        "test_player.png",
        "wb",
    ) as f:

        f.write(
            render(fake_player)
        )

    with open(
        "test_map.png",
        "wb",
    ) as f:

        f.write(
            render(fake_map)
        )

    print(
        "Imagens de teste geradas:"
    )

    print(
        "- test_player.png"
    )

    print(
        "- test_map.png"
    )