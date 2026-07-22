from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plugins.tracebook.skills.tracebook.scripts.project_registry import ensure_project
from plugins.tracebook.skills.tracebook.scripts.system_registry import (
    add_relation,
    bind_project,
    create_system,
    get_system,
    load_systems,
)


class SystemRegistryTest(unittest.TestCase):
    def test_system_membership_and_relations_are_explicit_and_stable(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "knowledge"
            (root / "01-projects").mkdir(parents=True)
            first_path = base / "payment-service"; first_path.mkdir()
            second_path = base / "order-service"; second_path.mkdir()
            first = ensure_project(root, first_path)
            second = ensure_project(root, second_path)

            system = create_system(root, "Commerce Platform")
            self.assertRegex(system.system_id, r"^sys-[0-9a-f]{32}$")
            self.assertRegex(system.relative_path, r"^04-systems/commerce-platform--[0-9a-f]{8}$")

            bound = bind_project(root, system.system_id, first.project_id)
            bound = bind_project(root, bound.system_id, second.project_id)
            related = add_relation(root, bound.system_id, first.project_id, second.project_id, "event")

            self.assertEqual((first.project_id, second.project_id), related.project_ids)
            self.assertEqual(1, len(related.relations))
            self.assertEqual(related, get_system(root, related.system_id))
            self.assertEqual((related,), load_systems(root))
            self.assertTrue((root / related.relative_path / "system.json").is_file())
            self.assertTrue((root / related.relative_path / "index.md").is_file())


if __name__ == "__main__":
    unittest.main()
