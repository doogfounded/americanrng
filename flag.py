#!/usr/bin/env python3
"""
Randomized ASCII American Flag Generator.
Generates an American flag in ASCII art with a randomized (or specified) number
of stars and stripes derived deterministically from a seed.
"""

import argparse
import hashlib
import math
import os
import random
import secrets
import sys
from typing import List, Optional, Tuple


# ANSI Escape Codes
ANSI_RESET = "\033[0m"
ANSI_CANTON = "\033[97;44;1m"     # Bright white bold text on blue background
ANSI_RED_STRIPE = "\033[31;41m"   # Red text on red background
ANSI_WHITE_STRIPE = "\033[37;107m"  # White text on bright white background


def derive_rng(seed_val: str) -> random.Random:
    """Create a deterministic Random instance from any string/integer seed."""
    digest = hashlib.sha256(seed_val.encode("utf-8")).digest()
    seed_int = int.from_bytes(digest, byteorder="big")
    return random.Random(seed_int)


def generate_random_seed() -> str:
    """Generate a readable 8-character alphanumeric seed."""
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    return "".join(secrets.choice(alphabet) for _ in range(8))


def solve_star_layout(num_stars: int) -> List[int]:
    """
    Given num_stars (1..100+), return a list of star counts per row.
    Evaluates rectangular, alternating (staggered), and symmetrically balanced
    row patterns, selecting the one with the best visual proportions for a flag canton.
    """
    if num_stars <= 0:
        return []
    if num_stars == 1:
        return [1]
    if num_stars == 2:
        return [2]

    target_aspect = 1.45  # Ideal cols / rows ratio in logical star counts
    best_rows: List[int] = [num_stars]
    best_score = float("inf")

    max_candidate_rows = min(num_stars, 12)
    for r in range(1, max_candidate_rows + 1):
        base_c = num_stars // r
        rem = num_stars % r
        if base_c == 0:
            continue

        max_c = base_c + (1 if rem > 0 else 0)
        aspect = max_c / r

        # Aspect ratio penalty (log scale so 2x too wide and 2x too tall are penalized equally)
        aspect_penalty = abs(math.log(aspect / target_aspect)) * 4.0

        # Pattern quality penalty:
        # 1. Exact rectangular grid (rem == 0)
        # 2. Classic alternating staggered grid (e.g. 6,5,6,5,6,5,6,5,6 for 50 stars: r is odd and rem == (r+1)//2 or rem == r//2)
        # 3. Even-row alternating grid (r is even and rem == r // 2)
        # 4. General symmetric distribution of remainder rows
        if rem == 0:
            pattern_penalty = 0.25  # Clean rectangle
        elif (r % 2 == 1 and (rem == (r + 1) // 2 or rem == r // 2)):
            pattern_penalty = 0.0   # Classic US flag staggered alternating pattern!
        elif (r % 2 == 0 and rem == r // 2):
            pattern_penalty = 0.15  # Even alternating staggered pattern
        else:
            pattern_penalty = 0.75  # Symmetric balanced rows

        # Avoid single long row if num_stars >= 4
        single_row_penalty = 5.0 if (r == 1 and num_stars >= 4) else 0.0

        score = aspect_penalty + pattern_penalty + single_row_penalty

        if score < best_score:
            best_score = score
            best_rows = _distribute_rows_symmetrically(r, base_c, rem)

    return best_rows


def _distribute_rows_symmetrically(r: int, base_c: int, rem: int) -> List[int]:
    """
    Distribute `rem` extra stars across `r` rows of `base_c` stars as evenly
    and symmetrically as possible (preferring alternating rows when applicable).
    """
    if rem == 0:
        return [base_c] * r

    # Classic odd-row alternating: e.g. r=9, rem=5 -> [c+1, c, c+1, c, c+1, c, c+1, c, c+1]
    if r % 2 == 1 and rem == (r + 1) // 2:
        return [base_c + 1 if i % 2 == 0 else base_c for i in range(r)]
    # Classic odd-row inner-alternating: e.g. r=9, rem=4 -> [c, c+1, c, c+1, c, c+1, c, c+1, c]
    if r % 2 == 1 and rem == r // 2:
        return [base_c + 1 if i % 2 == 1 else base_c for i in range(r)]
    # Even-row alternating: e.g. r=6, rem=3 -> [c+1, c, c+1, c, c+1, c]
    if r % 2 == 0 and rem == r // 2:
        return [base_c + 1 if i % 2 == 0 else base_c for i in range(r)]

    # General symmetric distribution from outside/center
    rows = [base_c] * r
    # Place pairs symmetrically from top and bottom moving inward, and middle if rem is odd
    left = 0
    right = r - 1
    remaining = rem
    if remaining % 2 == 1 and r % 2 == 1:
        rows[r // 2] += 1
        remaining -= 1

    step = max(1, (r // 2) // max(1, remaining // 2))
    idx = 0
    while remaining >= 2 and left < right:
        rows[left] += 1
        rows[right] += 1
        remaining -= 2
        left += 1
        right -= 1

    # Fallback if any left over
    for i in range(r):
        if remaining <= 0:
            break
        if rows[i] == base_c:
            rows[i] += 1
            remaining -= 1

    return rows


def compute_dimensions(
    star_rows: List[int], num_stripes: int
) -> Tuple[int, int, int, int, int, int, int]:
    """
    Compute adaptive dimensions for the flag:
    Returns (lines_per_stripe, total_height, total_width, canton_height, canton_width, col_step, v_step).
    """
    num_star_rows = len(star_rows)
    max_star_cols = max(star_rows) if star_rows else 1

    # Canton spans ceil(num_stripes / 2) stripes (e.g., 7 of 13 stripes on the US flag)
    canton_stripes = math.ceil(num_stripes / 2)

    # Determine lines_per_stripe so the canton is tall enough for the star rows
    # and total flag height stays comfortable on terminal (~12 to 36 lines)
    min_canton_height = max(num_star_rows, 3)
    lines_per_stripe = max(1, math.ceil(min_canton_height / canton_stripes))

    # If the flag has very few stripes (e.g., 3 to 6), thicken the stripes so the flag
    # isn't tiny, and if there is spare room, allow vertical spacing between star rows.
    if num_stripes * lines_per_stripe < 12:
        lines_per_stripe = max(lines_per_stripe, math.ceil(13 / num_stripes))

    canton_height = canton_stripes * lines_per_stripe
    total_height = num_stripes * lines_per_stripe

    # Choose uniform integer vertical step (1 or 2) between star rows
    if num_star_rows <= 1:
        v_step = 1
    elif canton_height >= (num_star_rows - 1) * 2 + 1:
        v_step = 2
    else:
        v_step = 1

    # Choose an even integer horizontal step (2, 4, 6...) between stars in a row
    # An even col_step guarantees that rows with (max_star_cols - 1) stars can be
    # staggered by exactly col_step // 2 columns with zero rounding jitter!
    min_canton_width = max(max_star_cols * 2 + 1, 9)
    ideal_total_width = max(
        int(round(total_height * 3.4)),
        int(math.ceil(min_canton_width / 0.42)),
        42,
    )
    target_canton_width = max(min_canton_width, int(round(ideal_total_width * 0.40)))

    if max_star_cols <= 1:
        col_step = 2
        canton_width = max(target_canton_width, 9)
    else:
        # Pick the closest even integer col_step >= 2 that fits within target_canton_width
        raw_step = (target_canton_width - 3) / (max_star_cols - 1)
        col_step = max(2, int(raw_step // 2) * 2)
        star_span = (max_star_cols - 1) * col_step + 1
        # Add symmetric left/right padding (at least 1 space on each side)
        pad = max(1, (target_canton_width - star_span) // 2)
        canton_width = star_span + 2 * pad

    total_width = max(ideal_total_width, int(round(canton_width / 0.40)))
    if total_width < canton_width + 16:
        total_width = canton_width + 20

    return (
        lines_per_stripe,
        total_height,
        total_width,
        canton_height,
        canton_width,
        col_step,
        v_step,
    )


def render_canton_grid(
    star_rows: List[int],
    canton_height: int,
    canton_width: int,
    col_step: int,
    v_step: int,
) -> List[str]:
    """
    Render the 2D character grid (`canton_height` rows x `canton_width` cols)
    for the canton containing `*` for stars and ` ` for empty space.
    """
    grid = [[" " for _ in range(canton_width)] for _ in range(canton_height)]
    num_rows = len(star_rows)
    if num_rows == 0:
        return ["".join(r) for r in grid]

    # Uniform vertical placement centered in canton_height
    total_v_span = (num_rows - 1) * v_step + 1
    start_y = max(0, (canton_height - total_v_span) // 2)

    for row_idx, count in enumerate(star_rows):
        y = start_y + row_idx * v_step
        if y >= canton_height or count <= 0:
            continue

        # Uniform horizontal placement centered in canton_width
        row_span = (count - 1) * col_step + 1
        start_x = max(0, (canton_width - row_span) // 2)

        for c in range(count):
            x = start_x + c * col_step
            if 0 <= x < canton_width:
                grid[y][x] = "*"

    return ["".join(r) for r in grid]


def build_flag_art(
    num_stars: int,
    num_stripes: int,
    use_color: bool = True,
    use_border: bool = True,
) -> str:
    """Build the complete ASCII American flag string."""
    star_rows = solve_star_layout(num_stars)
    (
        lines_per_stripe,
        total_height,
        total_width,
        canton_height,
        canton_width,
        col_step,
        v_step,
    ) = compute_dimensions(star_rows, num_stripes)

    canton_lines = render_canton_grid(
        star_rows, canton_height, canton_width, col_step, v_step
    )

    output_lines: List[str] = []

    if use_border:
        output_lines.append("+" + ("-" * total_width) + "+")

    for y in range(total_height):
        stripe_idx = y // lines_per_stripe
        is_red = (stripe_idx % 2 == 0)

        if y < canton_height:
            canton_part = canton_lines[y]
            if use_color:
                stripe_len = total_width - canton_width
                stripe_char = "#" if is_red else " "
                stripe_color = ANSI_RED_STRIPE if is_red else ANSI_WHITE_STRIPE
                line_body = (
                    f"{ANSI_CANTON}{canton_part}{ANSI_RESET}"
                    f"{stripe_color}{stripe_char * stripe_len}{ANSI_RESET}"
                )
            else:
                # Monochrome mode: use '|' on right edge of canton so canton boundary is crisp
                stripe_len = total_width - canton_width - 1
                stripe_char = "#" if is_red else "="
                line_body = f"{canton_part}|{stripe_char * stripe_len}"
        else:
            if use_color:
                stripe_char = "#" if is_red else " "
                stripe_color = ANSI_RED_STRIPE if is_red else ANSI_WHITE_STRIPE
                line_body = f"{stripe_color}{stripe_char * total_width}{ANSI_RESET}"
            else:
                stripe_char = "#" if is_red else "="
                line_body = stripe_char * total_width

        if use_border:
            output_lines.append(f"|{line_body}|")
        else:
            output_lines.append(line_body)

    if use_border:
        output_lines.append("+" + ("-" * total_width) + "+")

    return "\n".join(output_lines)


def enable_windows_ansi() -> None:
    """Enable virtual terminal processing on Windows consoles if applicable."""
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # STD_OUTPUT_HANDLE = -11, ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            pass


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a randomized ASCII American flag from a seed."
    )
    parser.add_argument(
        "seed_pos",
        nargs="?",
        default=None,
        metavar="seed",
        help="Optional seed (string or integer)",
    )
    parser.add_argument(
        "-s",
        "--seed",
        dest="seed_opt",
        default=None,
        help="Seed value (string or integer)",
    )
    parser.add_argument(
        "--stars",
        type=int,
        default=None,
        help="Override number of stars (default: randomized 1-100)",
    )
    parser.add_argument(
        "--stripes",
        type=int,
        default=None,
        help="Override number of stripes (default: randomized 3-25)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colors (pure monochrome ASCII mode)",
    )
    parser.add_argument(
        "--no-border",
        action="store_true",
        help="Omit outer ASCII border",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Only print the flag art (hide seed/metadata summary)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    seed_str = args.seed_opt if args.seed_opt is not None else args.seed_pos
    if seed_str is None:
        seed_str = generate_random_seed()
    else:
        seed_str = str(seed_str)

    rng = derive_rng(seed_str)
    num_stars = rng.randint(1, 100)
    num_stripes = rng.randint(3, 25)

    if args.stars is not None:
        if args.stars < 1:
            print("Error: --stars must be at least 1.", file=sys.stderr)
            return 1
        num_stars = args.stars

    if args.stripes is not None:
        if args.stripes < 2:
            print("Error: --stripes must be at least 2.", file=sys.stderr)
            return 1
        num_stripes = args.stripes

    use_color = not args.no_color and ("NO_COLOR" not in os.environ)
    if use_color:
        enable_windows_ansi()

    if not args.quiet:
        print(f"Seed: {seed_str} | Stars: {num_stars} | Stripes: {num_stripes}")

    art = build_flag_art(
        num_stars=num_stars,
        num_stripes=num_stripes,
        use_color=use_color,
        use_border=not args.no_border,
    )
    print(art)
    return 0


if __name__ == "__main__":
    sys.exit(main())
