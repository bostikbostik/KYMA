import urllib.request
import os
from PIL import Image, ImageDraw, ImageFont

def generate_banner(final_size, filename):
    SCALE = 2
    SIZE = final_size * SCALE
    
    img = Image.new('RGBA', (SIZE, SIZE), '#0a0a14')
    
    # Layout
    LOGO_W = int(SIZE * 0.85)
    S = LOGO_W / 440.0
    LOGO_H = int(120 * S)
    
    OFFSET_X = (SIZE - LOGO_W) // 2
    OFFSET_Y = (SIZE - LOGO_H) // 2
    
    ellipses = [
        {"cx": 60, "cy": 52, "rx": 36, "ry": 32, "fill": (233,30,140,255), "rot": -20},
        {"cx": 60, "cy": 52, "rx": 36, "ry": 28, "fill": (0,200,230, int(255*0.85)), "rot": 10},
        {"cx": 64, "cy": 60, "rx": 32, "ry": 24, "fill": (200,230,0, int(255*0.8)), "rot": 30},
        {"cx": 56, "cy": 68, "rx": 32, "ry": 24, "fill": (0,212,170, int(255*0.85)), "rot": -10},
    ]
    
    for el in ellipses:
        temp_size = int(120 * S)
        temp = Image.new('RGBA', (temp_size, temp_size), (0,0,0,0))
        temp_draw = ImageDraw.Draw(temp)
        
        # Center of ellipse
        ecx, ecy = el["cx"] * S, el["cy"] * S
        erx, ery = el["rx"] * S, el["ry"] * S
        
        temp_draw.ellipse((ecx - erx, ecy - ery, ecx + erx, ecy + ery), fill=el["fill"])
        
        # Rotate around center of 120x120 box, which is (60,60)
        temp = temp.rotate(-el["rot"], resample=Image.BICUBIC, expand=False)
        
        # Paste onto main image using alpha composite
        img.alpha_composite(temp, (OFFSET_X, OFFSET_Y))
        
    # Text
    font_size = int(76 * S)
    try:
        font = ImageFont.truetype("Outfit.ttf", font_size)
    except Exception as e:
        print(e)
        font = ImageFont.load_default()
        
    draw = ImageDraw.Draw(img)
    # Add spacing between letters manually
    text = "KYMA"
    x = OFFSET_X + int(140 * S)
    y = OFFSET_Y + int(18 * S)
    
    # We can just draw it since PIL handles fonts well, but tracking (letter-spacing) needs a workaround
    # Let's draw character by character for letter-spacing
    letter_spacing = int(10 * S)
    for char in text:
        draw.text((x, y), char, font=font, fill=(255,255,255,255))
        # Get character width
        bbox = draw.textbbox((0,0), char, font=font)
        char_width = bbox[2] - bbox[0]
        x += char_width + letter_spacing

    # Resize down for anti-aliasing
    final_img = img.resize((final_size, final_size), Image.LANCZOS)
    
    # Convert to CMYK
    cmyk_img = final_img.convert('CMYK')
    
    # Save as TIFF
    cmyk_img.save(filename, dpi=(150, 150), format="TIFF")
    print(f"Saved {filename}")

# Output the final 100x100 cm 150 DPI CMYK file
generate_banner(5906, "KYMA_FrontDesk_100x100cm_CMYK.tif")
