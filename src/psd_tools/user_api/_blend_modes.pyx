#cython: cdivision=True

"""
Cython extension with fast implementation of blend modes.
"""
from libc.stdlib cimport malloc, free, srand, rand
from libc.math cimport sqrt

ctypedef unsigned char  UINT8
ctypedef unsigned short UINT16
ctypedef unsigned int   UINT32

ctypedef struct Color:
    short r, g, b

# Resources:
#   Adobe PDF reference, section 7.2.4
#   http://wwwimages.adobe.com/content/dam/Adobe/en/devnet/pdf/pdfs/pdf_reference_1-7.pdf
#
#   http://www.venture-ware.com/kevin/coding/lets-learn-math-photoshop-blend-modes/
#   http://stackoverflow.com/questions/5919663/how-does-photoshop-blend-two-images-together
#   http://photoblogstop.com/photoshop/photoshop-blend-modes-explained

# Divide by 255 a fast way:
#   x / 255 = ((x + 1) * 257) >> 16     [0..65790)
#
# http://homepage.cs.uiowa.edu/~jones/bcd/divide.html
# http://www.agner.org/optimize/optimizing_assembly.pdf, section 16.9


# ============================================================================
# =============================   Normal group   =============================
# ============================================================================

# ============================================================================
#             ┌
#   f(A, B) = │B                , if A['A'] < rand() % 255 + 1
#             │(A['RGB'], 255)  , else
#             └
# ============================================================================
def dissolve(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef bytes res

    srand(314159265)

    for i in range(0, length, 4):
        if pdata2[3] < rand() % 255 + 1:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        else:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = 255

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res


# ============================================================================
# =============================   Darken group   =============================
# ============================================================================

# ============================================================================
#   f(a, b) = min(a, b)
# ============================================================================
def darken(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef UINT8 k, b, a
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            for k in range(3):
                b, a = pdata1[k], pdata2[k]

                if a < b:
                    pres[k] = a
                else:
                    pres[k] = b

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res

# ============================================================================
#   f(a, b) = a*b / 255
# ============================================================================
def multiply(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef UINT8 k, b, a
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            for k in range(3):
                b, a = pdata1[k], pdata2[k]

                pres[k] = ((a * b + 128) * 257) >> 16

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res

# ============================================================================
#   f(a, b) = max(0, 255 - (255 - b) * 255 / (1 if a == 0 else a))
# ============================================================================
def color_burn(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef UINT8 k, b, a
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            for k in range(3):
                b, a = pdata1[k], pdata2[k]

                if b == 255:
                    pres[k] = 255
                elif a == 255:
                    pres[k] = b
                elif <UINT8>~b >= a:
                    pres[k] = 0
                else:
                    b = ~b
                    pres[k] = ~(((b << 8) - b + (a >> 1)) / a)

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res

# ============================================================================
#   f(a, b) = max(0, a + b - 255)
# ============================================================================
def linear_burn(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef UINT8 k, b, a
    cdef UINT16 x
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            for k in range(3):
                b, a = pdata1[k], pdata2[k]

                x = a + b
                if x > 255:
                    pres[k] = x - 255
                else:
                    pres[k] = 0

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res

# ============================================================================
#             ┌
#   f(A, B) = │A, if get_lum(A) < get_lum(B)
#             │B, else
#             └
# ============================================================================
def darker_color(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef Color B, A
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            B.r = pdata1[0]
            B.g = pdata1[1]
            B.b = pdata1[2]

            A.r = pdata2[0]
            A.g = pdata2[1]
            A.b = pdata2[2]

            if get_lum(&A) < get_lum(&B):
                pres[0] = <UINT8>A.r
                pres[1] = <UINT8>A.g
                pres[2] = <UINT8>A.b
            else:
                pres[0] = <UINT8>B.r
                pres[1] = <UINT8>B.g
                pres[2] = <UINT8>B.b

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res


# ============================================================================
# ============================   Lighten group   =============================
# ============================================================================

# ============================================================================
#   f(a, b) = max(a, b)
# ============================================================================
def lighten(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef UINT8 k, b, a
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            for k in range(3):
                b, a = pdata1[k], pdata2[k]

                if a > b:
                    pres[k] = a
                else:
                    pres[k] = b

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res

# ============================================================================
#   f(a, b) = 255 - (255 - a)*(255 - b) / 255 = a + b - a*b / 255
# ============================================================================
def screen(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef UINT8 k, b, a
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            for k in range(3):
                b, a = pdata1[k], pdata2[k]

                pres[k] = a + b - (((a * b + 128) * 257) >> 16)

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res

# ============================================================================
#   f(a, b) = min(255, b * 255 / (1 if a == 255 else (255 - a)))
# ============================================================================
def color_dodge(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef UINT8 k, b, a
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            for k in range(3):
                b, a = pdata1[k], pdata2[k]

                if b == 0:
                    pres[k] = 0
                elif a == 0:
                    pres[k] = b
                elif b >= <UINT8>~a:
                    pres[k] = 255
                else:
                    a = ~a
                    pres[k] = ((b << 8) - b + (a >> 1)) / a

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res

# ============================================================================
#   f(a, b) = min(255, a + b)
# ============================================================================
def linear_dodge(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef UINT8 k, b, a
    cdef UINT16 x
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            for k in range(3):
                b, a = pdata1[k], pdata2[k]

                x = a + b
                if x < 255:
                    pres[k] = <UINT8>x
                else:
                    pres[k] = 255

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res

# ============================================================================
#             ┌
#   f(A, B) = │A, if get_lum(A) > get_lum(B)
#             │B, else
#             └
# ============================================================================
def lighter_color(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef Color B, A
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            B.r = pdata1[0]
            B.g = pdata1[1]
            B.b = pdata1[2]

            A.r = pdata2[0]
            A.g = pdata2[1]
            A.b = pdata2[2]

            if get_lum(&A) > get_lum(&B):
                pres[0] = <UINT8>A.r
                pres[1] = <UINT8>A.g
                pres[2] = <UINT8>A.b
            else:
                pres[0] = <UINT8>B.r
                pres[1] = <UINT8>B.g
                pres[2] = <UINT8>B.b

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res


# ============================================================================
# ============================   Contrast group   ============================
# ============================================================================

# ============================================================================
#             ┌
#   f(a, b) = │multiply(a, 2*b)     , if b < 128
#             │screen(a, 2*b - 255) , else
#             └
# ============================================================================
def overlay(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef UINT8 k, b, a
    cdef UINT16 x
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            for k in range(3):
                b, a = pdata1[k], pdata2[k]

                x = ((a * b + 64) * 0x10101) >> 23
                if b < 128:
                    pres[k] = <UINT8>x
                else:
                    pres[k] = (a + a) + (b + b) - x - 255

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res

# ============================================================================
#             ┌
#   f(a, b) = │b - (255 - 2*a)*b*(255 - b) / 255^2  , if a < 128
#             │b + (2*a - 255)*(D(b) - b) / 255     , else
#             └
#          ┌
#   D(x) = │((16*x - 12*255)*x + 4*(255^2))*x / 255^2   , if x < 64
#          │sqrt(x * 255)                               , else
#          └
# ============================================================================
def soft_light(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef UINT8 k, b, a, Db
    cdef UINT32 x
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            for k in range(3):
                b, a = pdata1[k], pdata2[k]

                if a < 128:
                    x = (255 - a - a)*b*(255 - b) + 32513
                    pres[k] = b - ((((x * 0x0203) >> 16) + x) >> 16)
                else:
                    if b < 64:
                        x = (((b << 4) - 3060)*b + 260100)*b + 32513
                        Db = (((x * 0x0C1) >> 15) + (x << 7) + x) >> 23
                    else:
                        Db = <UINT8>(sqrt(b * 255) + 0.5)
                    pres[k] = b + ((((a + a - 255)*(Db - b) + 128) * 257) >> 16)

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res

# ============================================================================
#                             ┌
#   f(a, b) = overlay(b, a) = │multiply(b, 2*a)     , if a < 128
#                             │screen(b, 2*a - 255) , else
#                             └
# ============================================================================
def hard_light(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef UINT8 k, b, a
    cdef UINT16 x
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            for k in range(3):
                b, a = pdata1[k], pdata2[k]

                x = ((a * b + 64) * 0x10101) >> 23
                if a < 128:
                    pres[k] = <UINT8>x
                else:
                    # Photoshop subtracts 256 here:
                    #   a += a - 256
                    #   pres[k] = a + b - (((a * b + 128) * 257) >> 16)
                    # Looks like a bug, as it should be an oposite of Overlay mode...
                    pres[k] = (a + a) + (b + b) - x - 255

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res

# ============================================================================
#             ┌
#   f(a, b) = │color_burn(2*a, b)       , if a < 128
#             │color_dodge(2*a - 255, b), else
#             └
# ============================================================================
def vivid_light(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef UINT8 k, b, a
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            for k in range(3):
                b, a = pdata1[k], pdata2[k]

                if a < 128:
                    # Here Photoshop sets result to "0" if a == 0,
                    #   but it doesn't do so in Color Burn mode.
                    # Looks like another bug...
                    if b == 255:
                        pres[k] = 255
                    elif <UINT8>~b >= a + a:
                        pres[k] = 0
                    else:
                        b = ~b
                        a += a
                        pres[k] = ~(((b << 8) - b + (a >> 1)) / a)
                else:
                    if b == 0:
                        pres[k] = 0
                    elif b >= <UINT8>((~a) + (~a)):
                        pres[k] = 255
                    else:
                        a = (~a) + (~a)
                        pres[k] = ((b << 8) - b + (a >> 1)) / a

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res

# ============================================================================
#             ┌
#   f(a, b) = │linear_burn(2*a, b)          , if a < 128
#             │linear_dodge(2*a - 255, b)   , else
#             └
# ============================================================================
def linear_light(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef UINT8 k, b, a
    cdef short x
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            for k in range(3):
                b, a = pdata1[k], pdata2[k]

                # Photoshop subtracts 256 here; it will shift results towards "0"...
                x = a + a + b - 255
                if a < 128:
                    if x >= 0:
                        pres[k] = <UINT8>x
                    else:
                        pres[k] = 0
                else:
                    if x <= 255:
                        pres[k] = <UINT8>x
                    else:
                        pres[k] = 255

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res

# ============================================================================
#             ┌
#   f(a, b) = │darken(2*a, b)       , if a < 128
#             │lighten(2*a - 255, b), else
#             └
# ============================================================================
def pin_light(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef UINT8 k, b, a
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            for k in range(3):
                b, a = pdata1[k], pdata2[k]

                if a < 128:
                    a += a
                    if a <= b:
                        pres[k] = a
                    else:
                        pres[k] = b
                else:
                    a += a - 255
                    if a >= b:
                        pres[k] = a
                    else:
                        pres[k] = b

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res

# ============================================================================
#             ┌                                ┌
#             │0    , if a + b < 255    g(x) = │255, if x < 128
#   f(a, b) = │255  , if a + b > 255           │0  , else
#             │g(a) , else                     └
#             └
# ============================================================================
def hard_mix(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef UINT8 k, b, a
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            for k in range(3):
                b, a = pdata1[k], pdata2[k]

                # this split evens the count of "0" and "255" values...
                if a < 128:
                    if a + b < 255:
                        pres[k] = 0
                    else:
                        pres[k] = 255
                else:
                    if a + b <= 255:
                        pres[k] = 0
                    else:
                        pres[k] = 255

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res


# ============================================================================
# ===========================   Inversion group   ============================
# ============================================================================

# ============================================================================
#   f(a, b) = |b - a|
# ============================================================================
def difference(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef UINT8 k, b, a
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            for k in range(3):
                b, a = pdata1[k], pdata2[k]

                if b > a:
                    pres[k] = b - a
                else:
                    pres[k] = a - b

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res

# ============================================================================
#   f(a, b) = a + b - 2*a*b / 255
# ============================================================================
def exclusion(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef UINT8 k, b, a
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            for k in range(3):
                b, a = pdata1[k], pdata2[k]

                pres[k] = a + b - (((a * b + 64) * 0x10101) >> 23)

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res


# ============================================================================
# ==========================   Cancellation group   ==========================
# ============================================================================

# ============================================================================
#   f(a, b) = max(0, b - a)
# ============================================================================
def subtract(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef UINT8 k, b, a
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            for k in range(3):
                b, a = pdata1[k], pdata2[k]

                if b > a:
                    pres[k] = b - a
                else:
                    pres[k] = 0

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res

# ============================================================================
#   f(a, b) = min(255, b * 255 / (1 if a == 0 else a))
# ============================================================================
def divide(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef UINT8 k, b, a
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            for k in range(3):
                b, a = pdata1[k], pdata2[k]

                if b == 0:
                    pres[k] = 0
                elif a == 255:
                    pres[k] = b
                elif b >= a:
                    pres[k] = 255
                else:
                    pres[k] = ((b << 8) - b + (a >> 1)) / a

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res


# ============================================================================
# ===========================   Component group   ============================
# ============================================================================

cdef short min(const Color *pcolor) nogil:
    if pcolor.r <= pcolor.g:
        if pcolor.r <= pcolor.b:
            return pcolor.r
        return pcolor.b
    else:
        if pcolor.g <= pcolor.b:
            return pcolor.g
        return pcolor.b

cdef short max(const Color *pcolor) nogil:
    if pcolor.r >= pcolor.g:
        if pcolor.r >= pcolor.b:
            return pcolor.r
        return pcolor.b
    else:
        if pcolor.g >= pcolor.b:
            return pcolor.g
        return pcolor.b

cdef void set_mmm(Color *pcolor, short **ppmin, short **ppmid, short **ppmax) nogil:
    if pcolor.r <= pcolor.g:
        if pcolor.r <= pcolor.b:
            ppmin[0] = &pcolor.r
            if pcolor.g <= pcolor.b:
                ppmid[0] = &pcolor.g
                ppmax[0] = &pcolor.b
            else:
                ppmid[0] = &pcolor.b
                ppmax[0] = &pcolor.g
        else:
            ppmin[0] = &pcolor.b
            ppmid[0] = &pcolor.r
            ppmax[0] = &pcolor.g
    else:
        if pcolor.g <= pcolor.b:
            ppmin[0] = &pcolor.g
            if pcolor.r <= pcolor.b:
                ppmid[0] = &pcolor.r
                ppmax[0] = &pcolor.b
            else:
                ppmid[0] = &pcolor.b
                ppmax[0] = &pcolor.r
        else:
            ppmin[0] = &pcolor.b
            ppmid[0] = &pcolor.g
            ppmax[0] = &pcolor.r

cdef inline UINT8 get_lum(const Color *pcolor) nogil:
    # color luminance according to YUV color space

    # Here Photoshop has something like a rounding error. This one fixes half of the deviations:
    #   return <UINT8>((30*pcolor.r/255.0 + 59*pcolor.g/255.0 + 11*pcolor.b/255.0) * 255 / 100 + 0.49999999999999)
    return ((30*pcolor.r + 59*pcolor.g + 11*pcolor.b + 51) * 0xA3D7) >> 22

cdef inline Color* set_lum(Color *pcolor, UINT8 new_lum) nogil:
    cdef short d = new_lum - get_lum(pcolor)
    pcolor.r += d
    pcolor.g += d
    pcolor.b += d
    return clip_color(pcolor)

cdef inline Color* clip_color(Color *pcolor) nogil:
    cdef UINT8 lum = get_lum(pcolor)
    cdef short n = min(pcolor)
    cdef short x = max(pcolor)
    cdef UINT8 divisor

    # second half of the deviations is somewhere in clipping formulas...
    if n < 0:
        if lum == 0:
            pcolor.r = pcolor.g = pcolor.b = 0
        else:
            divisor = lum - n

            pcolor.r -= lum
            if pcolor.r == divisor:
                pcolor.r = lum + lum
            else:
                pcolor.r = lum + (pcolor.r*lum + (divisor >> 1)) / divisor

            pcolor.g -= lum
            if pcolor.g == divisor:
                pcolor.g = lum + lum
            else:
                pcolor.g = lum + (pcolor.g*lum + (divisor >> 1)) / divisor

            pcolor.b -= lum
            if pcolor.b == divisor:
                pcolor.b = lum + lum
            else:
                pcolor.b = lum + (pcolor.b*lum + (divisor >> 1)) / divisor

    elif x > 255:
        if lum == 255:
            pcolor.r = pcolor.g = pcolor.b = 255
        else:
            divisor = x - lum

            pcolor.r -= lum
            if pcolor.r == divisor:
                pcolor.r = 255
            else:
                pcolor.r = lum + (pcolor.r*(255 - lum) + (divisor >> 1)) / divisor

            pcolor.g -= lum
            if pcolor.g == divisor:
                pcolor.g = 255
            else:
                pcolor.g = lum + (pcolor.g*(255 - lum) + (divisor >> 1)) / divisor

            pcolor.b -= lum
            if pcolor.b == divisor:
                pcolor.b = 255
            else:
                pcolor.b = lum + (pcolor.b*(255 - lum) + (divisor >> 1)) / divisor

    return pcolor

cdef inline UINT8 get_sat(const Color *pcolor) nogil:
    return max(pcolor) - min(pcolor)

cdef inline Color* set_sat(Color *pcolor, UINT8 new_sat) nogil:
    cdef UINT8 divisor, dividend
    cdef short *pmin = NULL
    cdef short *pmid = NULL
    cdef short *pmax = NULL
    set_mmm(pcolor, &pmin, &pmid, &pmax)

    divisor = pmax[0] - pmin[0]
    if divisor == 0 or new_sat == 0:
        pmid[0] = pmax[0] = 0
    else:
        dividend = pmid[0] - pmin[0]
        if dividend == divisor:
            pmid[0] = pmax[0] = new_sat
        else:
            pmid[0] = (dividend*new_sat + (divisor >> 1)) / divisor
            pmax[0] = new_sat
    pmin[0] = 0

    return pcolor

# ============================================================================
#   f(A, B) = set_lum(set_sat(A, get_sat(B)), get_lum(B))
# ============================================================================
def hue(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef Color B, A
    cdef Color *X
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            B.r = pdata1[0]
            B.g = pdata1[1]
            B.b = pdata1[2]

            A.r = pdata2[0]
            A.g = pdata2[1]
            A.b = pdata2[2]

            X = set_lum(set_sat(&A, get_sat(&B)), get_lum(&B))
            pres[0] = <UINT8>X.r
            pres[1] = <UINT8>X.g
            pres[2] = <UINT8>X.b

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res

# ============================================================================
#   f(A, B) = set_lum(set_sat(B, get_sat(A)), get_lum(B))
# ============================================================================
def saturation(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef Color B, A
    cdef Color *X
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            B.r = pdata1[0]
            B.g = pdata1[1]
            B.b = pdata1[2]

            A.r = pdata2[0]
            A.g = pdata2[1]
            A.b = pdata2[2]

            X = set_lum(set_sat(&B, get_sat(&A)), get_lum(&B))
            pres[0] = <UINT8>X.r
            pres[1] = <UINT8>X.g
            pres[2] = <UINT8>X.b

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res

# ============================================================================
#   f(A, B) = set_lum(A, get_lum(B))
# ============================================================================
def color(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef Color B, A
    cdef Color *X
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            B.r = pdata1[0]
            B.g = pdata1[1]
            B.b = pdata1[2]

            A.r = pdata2[0]
            A.g = pdata2[1]
            A.b = pdata2[2]

            X = set_lum(&A, get_lum(&B))
            pres[0] = <UINT8>X.r
            pres[1] = <UINT8>X.g
            pres[2] = <UINT8>X.b

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res

# ============================================================================
#   f(A, B) = set_lum(B, get_lum(A))
# ============================================================================
def luminosity(bytes imdata1, bytes imdata2):
    cdef size_t i, length = len(imdata1)
    cdef UINT8 *pdata1 = imdata1
    cdef UINT8 *pdata2 = imdata2
    cdef UINT8 *pres = <UINT8 *>malloc(length)
    cdef Color B, A
    cdef Color *X
    cdef bytes res

    for i in range(0, length, 4):
        if pdata2[3] == 0:
            pres[0] = pdata1[0]
            pres[1] = pdata1[1]
            pres[2] = pdata1[2]
            pres[3] = pdata1[3]
        elif pdata1[3] == 0:
            pres[0] = pdata2[0]
            pres[1] = pdata2[1]
            pres[2] = pdata2[2]
            pres[3] = pdata2[3]
        else:
            B.r = pdata1[0]
            B.g = pdata1[1]
            B.b = pdata1[2]

            A.r = pdata2[0]
            A.g = pdata2[1]
            A.b = pdata2[2]

            X = set_lum(&B, get_lum(&A))
            pres[0] = <UINT8>X.r
            pres[1] = <UINT8>X.g
            pres[2] = <UINT8>X.b

            pres[3] = pdata2[3]

        pdata1 += 4
        pdata2 += 4
        pres += 4

    pres -= length
    res = pres[:length]
    free(pres)
    return res
