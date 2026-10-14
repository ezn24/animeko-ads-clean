"""Regression checks for upstream changes that broke the old unified diff."""
from pathlib import Path
import tempfile
import unittest
if __package__:
    from . import patch_source as patcher
else:
    import patch_source as patcher


RECOMMENDATION = '''
class GetSubjectRecommendationUseCaseImpl(private val service: SubjectService) {
    override suspend fun invoke(subjectId: Int): List<SubjectRecommendation> {
        return service.getSubjectRecommendations(subjectId, 15).map {
            SubjectRecommendation(subjectId = it.subjectId)
        }
    }
}
'''
UPDATER = '''
class UpdateChecker {
    suspend fun checkLatestVersion(
        releaseClass: ReleaseClass,
        currentVersion: String = currentAniBuildConfig.versionName,
    ): NewVersion? {
        HttpClient(getPlatformKtorEngine()) { expectSuccess = true }.use { client ->
            return client.getVersionFromAniServer()
        }
    }
}
'''


class PatchTests(unittest.TestCase):
    def test_imports_comments_crlf_and_formatting_do_not_break_changes(self):
        original = ('import me.him188.ani.utils.platform.isAndroidTv\n' + RECOMMENDATION
                    .replace('return service.getSubjectRecommendations(subjectId, 15).map {',
                             'return service /* changed */ . getSubjectRecommendations (\n'
                             '            subjectId, 15\n        )\n        .map {'))
        original = original.replace('\n', '\r\n')
        patched = patcher.recommendation(original)
        self.assertIn(patcher.FILTER, patched)
        self.assertEqual(patcher.recommendation(patched), patched)
        updated = patcher.updater('import new.api.Update\n' + UPDATER)
        self.assertIn(patcher.GUARD, updated)
        self.assertEqual(patcher.updater(updated), updated)

    def test_comments_and_literals_are_not_transformation_targets(self):
        fake = '// class UpdateChecker { fun checkLatestVersion() {} }\n'
        fake += 'val sample = "class UpdateChecker { fun checkLatestVersion() {} }"\n'
        updated = patcher.updater(fake + UPDATER)
        self.assertTrue(updated.startswith(fake))
        self.assertEqual(updated.count(patcher.GUARD), 1)

    def test_function_overloads_and_changed_pipeline_fail_closed(self):
        with self.assertRaises(patcher.CompatibilityError):
            patcher.updater(UPDATER.replace('class UpdateChecker {',
                                           'class UpdateChecker { fun checkLatestVersion() {}'))
        with self.assertRaises(patcher.CompatibilityError):
            patcher.recommendation(RECOMMENDATION.replace('.map {', '.take(10).map {'))

    def test_relocated_files_and_transactional_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / 'app/moved/src/commonMain/kotlin/renamed'
            folder.mkdir(parents=True)
            recommendation = folder / 'Recommendation.kt'
            updater = folder / 'Updater.kt'
            recommendation.write_text(RECOMMENDATION, encoding='utf-8')
            updater.write_text(UPDATER, encoding='utf-8')
            patcher.apply(root, check=True)
            self.assertEqual(recommendation.read_text(encoding='utf-8'), RECOMMENDATION)
            updater.write_text('class UpdateChecker {}', encoding='utf-8')
            with self.assertRaises(patcher.CompatibilityError):
                patcher.apply(root)
            self.assertEqual(recommendation.read_text(encoding='utf-8'), RECOMMENDATION)
            updater.write_text(UPDATER, encoding='utf-8')
            patcher.apply(root)
            self.assertIn(patcher.FILTER, recommendation.read_text(encoding='utf-8'))
            self.assertIn(patcher.GUARD, updater.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
