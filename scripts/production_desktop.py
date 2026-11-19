"""Local-only UI for the separately approved production snapshot transfer."""
import argparse
from scripts.production_transfer import execute
from scripts.stage_desktop import show_form


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply-approved', action='store_true')
    args = parser.parse_args()
    show_form(execute, allow_create=args.apply_approved, with_progress=True,
        title='Academy AI — перенос 40 XP в рабочую базу',
        heading='Рабочая база · перенос копии профиля с 40 XP',
        create_label='Перенести копию 40 XP')


if __name__ == '__main__':
    main()
