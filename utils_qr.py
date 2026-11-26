"""Generador ligero de códigos QR en formato SVG (sin dependencias externas).
Implementa QR Code Model 2 (modo byte, corrección de errores L, versiones 1-6).
"""


def _gf_mul(a: int, b: int) -> int:
    r = 0
    while b:
        if b & 1:
            r ^= a
        a <<= 1
        if a & 0x100:
            a ^= 0x11D
        b >>= 1
    return r


def _rs_gen_poly(degree: int) -> list[int]:
    g = [1]
    exp = 1
    for _ in range(degree):
        ng = [0] * (len(g) + 1)
        for i, c in enumerate(g):
            ng[i] ^= c
            ng[i + 1] ^= _gf_mul(c, exp)
        g = ng
        exp = _gf_mul(exp, 2)
    return g


def _rs_encode(data: list[int], ec_len: int) -> list[int]:
    gen = _rs_gen_poly(ec_len)
    res = list(data) + [0] * ec_len
    for i in range(len(data)):
        coef = res[i]
        if coef:
            for j in range(1, len(gen)):
                res[i + j] ^= _gf_mul(gen[j], coef)
    return res[len(data):]


# Capacidad en bytes (EC Level L) para versiones 1..6: (version, total_codewords, ec_codewords, align_pos)
_VER_INFO = [
    (1, 26, 7, []),
    (2, 44, 10, [18]),
    (3, 70, 15, [22]),
    (4, 100, 20, [26]),
    (5, 134, 26, [30]),
    (6, 172, 18, [34]),  # 2 bloques en v6; usamos v1..v5 (hasta 106 bytes) y truncamos si excede
]


def generar_qr_matriz(texto: str) -> list[list[bool]]:
    raw = texto.encode("utf-8")[:104]
    ver, total_cw, ec_cw, align = _VER_INFO[4]
    for v, tcw, ecw, al in _VER_INFO[:5]:
        data_cap = tcw - ecw
        if len(raw) + 2 <= data_cap:
            ver, total_cw, ec_cw, align = v, tcw, ecw, al
            break

    data_cw = total_cw - ec_cw
    bits = [0, 1, 0, 0]  # Byte mode (0100)
    for b in range(7, -1, -1):
        bits.append((len(raw) >> b) & 1)
    for byte in raw:
        for b in range(7, -1, -1):
            bits.append((byte >> b) & 1)
    for _ in range(min(4, data_cw * 8 - len(bits))):
        bits.append(0)
    while len(bits) % 8:
        bits.append(0)
    cw = [int("".join(str(x) for x in bits[i:i + 8]), 2) for i in range(0, len(bits), 8)]
    pad = [0xEC, 0x11]
    idx = 0
    while len(cw) < data_cw:
        cw.append(pad[idx % 2])
        idx += 1

    ec = _rs_encode(cw, ec_cw)
    all_cw = cw + ec
    stream = []
    for byte in all_cw:
        for b in range(7, -1, -1):
            stream.append((byte >> b) & 1)

    size = 17 + 4 * ver
    grid = [[None] * size for _ in range(size)]
    func = [[False] * size for _ in range(size)]

    def set_mod(r, c, val, is_func=True):
        if 0 <= r < size and 0 <= c < size:
            grid[r][c] = bool(val)
            if is_func:
                func[r][c] = True

    def draw_finder(r0, c0):
        for r in range(-1, 8):
            for c in range(-1, 8):
                if 0 <= r < 7 and 0 <= c < 7:
                    val = (r in (0, 6) or c in (0, 6) or (2 <= r <= 4 and 2 <= c <= 4))
                else:
                    val = False
                set_mod(r0 + r, c0 + c, val, True)

    draw_finder(0, 0)
    draw_finder(0, size - 7)
    draw_finder(size - 7, 0)

    if align:
        pos = align[0]
        for r in range(-2, 3):
            for c in range(-2, 3):
                val = max(abs(r), abs(c)) != 1
                set_mod(pos + r, pos + c, val, True)

    for i in range(8, size - 8):
        set_mod(6, i, i % 2 == 0, True)
        set_mod(i, 6, i % 2 == 0, True)

    set_mod(size - 8, 8, True, True)
    for i in range(9):
        if i != 6:
            func[8][i] = True
            func[i][8] = True
    for i in range(8):
        func[8][size - 1 - i] = True
        func[size - 1 - i][8] = True

    # Colocar datos en zigzag
    bit_i = 0
    col = size - 1
    up = True
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if up else range(size)
        for r in rows:
            for dc in (0, -1):
                c = col + dc
                if not func[r][c]:
                    b = stream[bit_i] if bit_i < len(stream) else 0
                    bit_i += 1
                    # Mask 0: (r + c) % 2 == 0
                    if (r + c) % 2 == 0:
                        b ^= 1
                    grid[r][c] = bool(b)
        up = not up
        col -= 2

    # Format info: EC=L (01), Mask=0 (000) -> 01000 -> BCH -> 111011111000100
    fmt = 0b111011111000100
    for i in range(15):
        bit = bool((fmt >> (14 - i)) & 1)
        if i < 6:
            grid[8][i] = bit
        elif i < 8:
            grid[8][i + 1] = bit
        else:
            grid[8][size - 15 + i] = bit
        if i < 8:
            grid[size - 1 - i][8] = bit
        elif i < 9:
            grid[7][8] = bit
        else:
            grid[14 - i][8] = bit

    return [[bool(x) for x in row] for row in grid]


def qr_svg(texto: str, tam: int = 160) -> str:
    """Devuelve un SVG limpio del código QR para incrustar o servir por HTTP."""
    mat = generar_qr_matriz(texto)
    n = len(mat)
    quiet = 2
    total = n + quiet * 2
    rects = []
    for r, row in enumerate(mat):
        for c, val in enumerate(row):
            if val:
                rects.append(f'<rect x="{c + quiet}" y="{r + quiet}" width="1" height="1"/>')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total} {total}" '
        f'width="{tam}" height="{tam}" shape-rendering="crispEdges">'
        f'<rect width="100%" height="100%" fill="#ffffff"/>'
        f'<g fill="#0d3b66">{"".join(rects)}</g></svg>'
    )
