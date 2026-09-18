#!/usr/bin/env python3
"""
Create browser extension icons with microphone design
"""
import os
import sys

def create_icon_svg(size, output_path):
    """Create SVG icon with microphone"""
    # Manor-AI brand colors
    bg_color = "#0f766e"  # Teal
    icon_color = "#ffffff"  # White
    accent_color = "#0d9488"  # Lighter teal
    
    svg_content = f'''<svg width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bgGradient" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:{bg_color};stop-opacity:1" />
      <stop offset="100%" style="stop-color:{accent_color};stop-opacity:1" />
    </linearGradient>
  </defs>
  
  <!-- Background with rounded corners -->
  <rect width="{size}" height="{size}" rx="{size // 4}" fill="url(#bgGradient)"/>
  
  <!-- Microphone body -->
  <rect x="{size * 0.35}" y="{size * 0.25}" width="{size * 0.3}" height="{size * 0.4}" 
        rx="{size * 0.05}" fill="{icon_color}"/>
  
  <!-- Microphone stand -->
  <rect x="{size * 0.25}" y="{size * 0.65}" width="{size * 0.5}" height="{size * 0.08}" 
        rx="{size * 0.02}" fill="{icon_color}"/>
  
  <!-- Microphone cord -->
  <rect x="{size * 0.35}" y="{size * 0.73}" width="{size * 0.3}" height="{size * 0.05}" 
        rx="{size * 0.01}" fill="{icon_color}" opacity="0.8"/>
  
  <!-- Sound waves (optional decorative element) -->
  <circle cx="{size * 0.2}" cy="{size * 0.45}" r="{size * 0.08}" fill="none" 
          stroke="{icon_color}" stroke-width="{size * 0.02}" opacity="0.3"/>
  <circle cx="{size * 0.8}" cy="{size * 0.45}" r="{size * 0.08}" fill="none" 
          stroke="{icon_color}" stroke-width="{size * 0.02}" opacity="0.3"/>
</svg>'''
    
    with open(output_path, 'w') as f:
        f.write(svg_content)
    print(f'✅ Created {output_path}')

def create_icon_png_pil(size, output_path):
    """Create PNG icon using PIL"""
    try:
        from PIL import Image, ImageDraw
        
        # Create image with transparency
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Manor-AI brand colors
        bg_color = (15, 118, 110)  # #0f766e - Teal
        accent_color = (13, 148, 136)  # #0d9488 - Lighter teal
        icon_color = (255, 255, 255)  # White
        
        # Draw rounded rectangle background with gradient effect
        margin = size // 8
        corner_radius = size // 4
        
        # Background (simplified gradient - solid color for now)
        draw.rounded_rectangle(
            [margin, margin, size - margin, size - margin],
            radius=corner_radius,
            fill=bg_color
        )
        
        # Microphone body (vertical rectangle)
        mic_width = int(size * 0.3)
        mic_height = int(size * 0.4)
        mic_x = (size - mic_width) // 2
        mic_y = int(size * 0.25)
        draw.rounded_rectangle(
            [mic_x, mic_y, mic_x + mic_width, mic_y + mic_height],
            radius=int(size * 0.05),
            fill=icon_color
        )
        
        # Microphone stand (horizontal line at bottom)
        stand_width = int(size * 0.5)
        stand_height = int(size * 0.08)
        stand_x = (size - stand_width) // 2
        stand_y = int(size * 0.65)
        draw.rounded_rectangle(
            [stand_x, stand_y, stand_x + stand_width, stand_y + stand_height],
            radius=int(size * 0.02),
            fill=icon_color
        )
        
        # Microphone cord (small line below stand)
        cord_width = int(size * 0.3)
        cord_height = int(size * 0.05)
        cord_x = (size - cord_width) // 2
        cord_y = int(size * 0.73)
        draw.rounded_rectangle(
            [cord_x, cord_y, cord_x + cord_width, cord_y + cord_height],
            radius=int(size * 0.01),
            fill=icon_color
        )
        
        # Sound waves (decorative)
        wave_radius = int(size * 0.08)
        draw.ellipse(
            [int(size * 0.2) - wave_radius, int(size * 0.45) - wave_radius,
             int(size * 0.2) + wave_radius, int(size * 0.45) + wave_radius],
            outline=icon_color,
            width=max(1, int(size * 0.02))
        )
        draw.ellipse(
            [int(size * 0.8) - wave_radius, int(size * 0.45) - wave_radius,
             int(size * 0.8) + wave_radius, int(size * 0.45) + wave_radius],
            outline=icon_color,
            width=max(1, int(size * 0.02))
        )
        
        img.save(output_path, 'PNG')
        print(f'✅ Created {output_path} ({size}x{size})')
        return True
        
    except ImportError:
        return False
    except Exception as e:
        print(f'❌ Error creating PNG with PIL: {e}')
        return False

def convert_svg_to_png(size, svg_path, png_path):
    """Convert SVG to PNG using external tools"""
    # Try using rsvg-convert (librsvg)
    try:
        import subprocess
        result = subprocess.run(
            ['rsvg-convert', '-w', str(size), '-h', str(size), '-o', png_path, svg_path],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            print(f'✅ Converted {svg_path} to {png_path} ({size}x{size})')
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    # Try using inkscape
    try:
        import subprocess
        result = subprocess.run(
            ['inkscape', svg_path, '--export-filename', png_path, f'--export-width={size}', f'--export-height={size}'],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            print(f'✅ Converted {svg_path} to {png_path} ({size}x{size})')
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    return False

if __name__ == '__main__':
    os.makedirs('icons', exist_ok=True)
    
    sizes = [16, 48, 128]
    
    # Try PIL first (best quality)
    pil_success = True
    for size in sizes:
        png_path = f'icons/icon{size}.png'
        if not create_icon_png_pil(size, png_path):
            pil_success = False
            break
    
    if not pil_success:
        print('\n⚠️ PIL not available, trying alternative methods...')
        
        # Create SVG files
        svg_files = []
        for size in sizes:
            svg_path = f'icons/icon{size}.svg'
            create_icon_svg(size, svg_path)
            svg_files.append((size, svg_path))
        
        # Try to convert SVG to PNG
        converted = False
        for size, svg_path in svg_files:
            png_path = f'icons/icon{size}.png'
            if convert_svg_to_png(size, svg_path, png_path):
                converted = True
                os.remove(svg_path)  # Clean up SVG after conversion
        
        if not converted:
            print('\n⚠️ Could not convert SVG to PNG automatically.')
            print('Please install one of:')
            print('  - Pillow: pip install Pillow')
            print('  - librsvg: brew install librsvg (macOS) or apt-get install librsvg2-bin (Linux)')
            print('  - Inkscape: brew install inkscape (macOS)')
            print('\nSVG files have been created in icons/ directory.')
            print('You can manually convert them or use an online tool.')
    else:
        print('\n✅ All icons created successfully using PIL!')
