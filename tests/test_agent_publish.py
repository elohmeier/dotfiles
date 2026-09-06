from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from scripts.agent_publish import cli


class AgentPublishTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.addCleanup(patch.stopall)
        patch(
            "scripts.agent_publish.data_root",
            return_value=self.root / "data" / "agent-publish",
        ).start()
        patch(
            "scripts.agent_publish.state_path",
            return_value=self.root / "state" / "agent-publish" / "state.json",
        ).start()
        self.runner = CliRunner()

    def test_register_and_manage_assets(self) -> None:
        project = self.root / "Example Project"
        project.mkdir()
        video = self.root / "demo.mp4"
        video.write_bytes(b"video")

        result = self.runner.invoke(cli, ["register", str(project)])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue(result.output.strip().endswith("agent-publish/example-project"))

        result = self.runner.invoke(
            cli, ["add", str(video), "--project", str(project), "--to", "videos"]
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(
            result.output.strip(),
            "http://localhost:8064/example-project/videos/demo.mp4",
        )

        result = self.runner.invoke(cli, ["assets", "example-project"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("videos/demo.mp4\t5\t", result.output)

        result = self.runner.invoke(cli, ["unregister", "example-project"])
        self.assertEqual(result.exit_code, 2)
        self.assertIn("--delete-assets", result.output)

        result = self.runner.invoke(
            cli, ["remove", "videos/demo.mp4", "--project", "example-project"]
        )
        self.assertEqual(result.exit_code, 0, result.output)

        result = self.runner.invoke(cli, ["unregister", "example-project"])
        self.assertEqual(result.exit_code, 0, result.output)

    def test_registration_is_idempotent_and_slugs_do_not_collide(self) -> None:
        first = self.root / "one" / "demo"
        second = self.root / "two" / "demo"
        first.mkdir(parents=True)
        second.mkdir(parents=True)

        self.assertEqual(self.runner.invoke(cli, ["register", str(first)]).exit_code, 0)
        self.assertEqual(self.runner.invoke(cli, ["register", str(first)]).exit_code, 0)
        result = self.runner.invoke(cli, ["register", str(second)])
        self.assertEqual(result.exit_code, 2)
        self.assertIn("already belongs", result.output)

    def test_configured_url_is_stored_and_used(self) -> None:
        project = self.root / "demo"
        project.mkdir()
        self.assertEqual(
            self.runner.invoke(cli, ["register", str(project)]).exit_code, 0
        )

        result = self.runner.invoke(
            cli, ["configure", "--url", "http://halo.example:8064/"]
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(result.output.strip(), "http://halo.example:8064")

        result = self.runner.invoke(cli, ["url", "demo"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(result.output.strip(), "http://halo.example:8064/demo/")

    def test_asset_paths_cannot_leave_project_directory(self) -> None:
        project = self.root / "demo"
        project.mkdir()
        self.assertEqual(
            self.runner.invoke(cli, ["register", str(project)]).exit_code, 0
        )

        result = self.runner.invoke(
            cli, ["remove", "../state.json", "--project", "demo"]
        )
        self.assertEqual(result.exit_code, 2)
        self.assertIn("leaves the project directory", result.output)

    def test_key_replaces_one_managed_asset_and_cleans_old_extension(self) -> None:
        project = self.root / "demo"
        project.mkdir()
        first = self.root / "first.mp4"
        first.write_bytes(b"first")
        second = self.root / "second.webm"
        second.write_bytes(b"second")
        self.assertEqual(
            self.runner.invoke(cli, ["register", str(project)]).exit_code, 0
        )

        result = self.runner.invoke(
            cli,
            [
                "add",
                str(first),
                "--project",
                str(project),
                "--to",
                "videos",
                "--key",
                "level-one",
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue(
            (self.root / "data/agent-publish/demo/videos/level-one.mp4").is_file()
        )

        result = self.runner.invoke(
            cli,
            [
                "add",
                str(second),
                "--project",
                str(project),
                "--to",
                "videos",
                "--key",
                "level-one",
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        published = self.root / "data/agent-publish/demo/videos"
        self.assertFalse((published / "level-one.mp4").exists())
        self.assertEqual((published / "level-one.webm").read_bytes(), b"second")
        state = json.loads((self.root / "state/agent-publish/state.json").read_text())
        self.assertEqual(
            state["projects"]["demo"]["assets"]["level-one"],
            "videos/level-one.webm",
        )

        result = self.runner.invoke(
            cli, ["remove", "--project", "demo", "--key", "level-one"]
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertFalse((published / "level-one.webm").exists())


if __name__ == "__main__":
    unittest.main()
