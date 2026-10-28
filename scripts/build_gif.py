"""Encode captured UI frames as a silent loop without changing their content."""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    media = ROOT / "docs/media"
    frames = []
    for index in (1, 2, 3):
        with Image.open(media / f"proof-frame-{index:02}.png") as image:
            frames.append(image.convert("RGB"))
    frames[0].save(
        media / "policydesk-proof.gif",
        save_all=True,
        append_images=frames[1:],
        duration=[1800, 1800, 2600],
        loop=0,
        optimize=False,
        disposal=2,
    )
    print(
        "Encoded actual approval, authorization and refusal frames as docs/media/policydesk-proof.gif"
    )


if __name__ == "__main__":
    main()
