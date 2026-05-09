"""Daily orchestrator: fetch new papers, then classify any unclassified ones."""
from . import fetch, classify


def main():
    print("=== Fetching new papers ===")
    fetch.run()
    print("\n=== Classifying ===")
    classify.run()
    print("\nDone.")


if __name__ == "__main__":
    main()
