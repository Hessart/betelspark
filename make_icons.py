from PIL import Image, ImageDraw


def make_icon(size, path):
    img = Image.new("RGB", (size, size), "#0f1220")
    draw = ImageDraw.Draw(img)
    c = size / 2
    r = size * 0.36   # długość ramion iskry
    w = size * 0.07   # szerokość "talii"
    points = [
        (c, c - r), (c + w, c - w), (c + r, c), (c + w, c + w),
        (c, c + r), (c - w, c + w), (c - r, c), (c - w, c - w),
    ]
    draw.polygon(points, fill="#ff7a45")
    img.save(path)


make_icon(192, "icon-192.png")
make_icon(512, "icon-512.png")
print("Gotowe: icon-192.png i icon-512.png")