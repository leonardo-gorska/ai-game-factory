"""Tests for backend.core.build_predictor"""

from unittest.mock import MagicMock

from backend.core.build_predictor import (
    BuildPredictor,
    BuildPrediction,
    REVIEW_THRESHOLD,
)


class TestBuildPredictorBasic:
    def test_empty_input_low_risk(self):
        bp = BuildPredictor()
        pred = bp.predict()
        assert pred.failure_probability < REVIEW_THRESHOLD
        assert pred.should_review is False

    def test_prediction_returns_build_prediction(self):
        bp = BuildPredictor()
        pred = bp.predict(code_changes="x = 1\n")
        assert isinstance(pred, BuildPrediction)

    def test_to_dict(self):
        pred = BuildPrediction(
            failure_probability=0.72,
            risk_factors=["Large diff"],
            should_review=True,
            confidence=0.5,
        )
        d = pred.to_dict()
        assert d["failure_probability"] == 0.72
        assert d["should_review"] is True
        assert "Large diff" in d["risk_factors"]


class TestBuildPredictorDiffRisk:
    def test_large_diff_high_risk(self):
        bp = BuildPredictor()
        big_diff = "\n".join([f"line {i}" for i in range(600)])
        pred = bp.predict(code_changes=big_diff, total_lines=1000)
        # 600/1000 = 60% — should be high
        assert pred.failure_probability > 0.2
        assert any("diff" in f.lower() for f in pred.risk_factors)

    def test_small_diff_low_risk(self):
        bp = BuildPredictor()
        small_diff = "x = 1\ny = 2\n"
        pred = bp.predict(code_changes=small_diff, total_lines=10000)
        assert pred.failure_probability < REVIEW_THRESHOLD


class TestBuildPredictorImports:
    def test_new_imports_increase_risk(self):
        bp = BuildPredictor()
        pred_no_imports = bp.predict(changed_files_count=1)
        pred_with_imports = bp.predict(
            changed_files_count=1, has_new_imports=True,
        )
        assert pred_with_imports.failure_probability >= pred_no_imports.failure_probability

    def test_many_import_lines_in_diff(self):
        bp = BuildPredictor()
        diff = "\n".join([
            f"+ import module_{i}" for i in range(10)
        ])
        pred = bp.predict(code_changes=diff)
        assert any("import" in f.lower() for f in pred.risk_factors)


class TestBuildPredictorFileCount:
    def test_many_files_increase_risk(self):
        bp = BuildPredictor()
        pred_few = bp.predict(changed_files_count=1)
        pred_many = bp.predict(changed_files_count=20)
        assert pred_many.failure_probability > pred_few.failure_probability
        assert any("files" in f.lower() for f in pred_many.risk_factors)


class TestBuildPredictorHistory:
    def test_failure_streak_increases_risk(self):
        bp = BuildPredictor()
        # Seed with failures
        for _ in range(5):
            bp.calibrate(build_succeeded=False)

        pred = bp.predict(changed_files_count=2)
        assert any("failure" in f.lower() for f in pred.risk_factors)

    def test_success_streak_lowers_risk(self):
        bp = BuildPredictor()
        for _ in range(5):
            bp.calibrate(build_succeeded=True)

        pred = bp.predict(changed_files_count=2)
        history_factors = [f for f in pred.risk_factors if "failure" in f.lower()]
        assert len(history_factors) == 0


class TestBuildPredictorErrorPatterns:
    def test_with_error_pattern_db(self):
        db = MagicMock()
        db.lookup = MagicMock(return_value={"pattern": "x", "fix": "y"})

        bp = BuildPredictor()
        diff = "\n".join([f"some error prone line number {i} with details" for i in range(10)])
        pred = bp.predict(code_changes=diff, error_pattern_db=db)
        # Should have made calls to lookup
        assert db.lookup.call_count > 0

    def test_without_error_pattern_db(self):
        bp = BuildPredictor()
        pred = bp.predict(code_changes="some code\n" * 10)
        # Should not crash without error_pattern_db
        assert isinstance(pred, BuildPrediction)


class TestBuildPredictorCalibration:
    def test_calibrate_tracks_history(self):
        bp = BuildPredictor()
        bp.predict(code_changes="x\n")
        bp.calibrate(build_succeeded=True)
        assert len(bp._history) == 1
        assert bp._history[0] is True

    def test_calibrate_trims_old_history(self):
        bp = BuildPredictor()
        for i in range(30):
            bp.predict(code_changes=f"line {i}\n")
            bp.calibrate(build_succeeded=i % 2 == 0)
        assert len(bp._history) <= 20

    def test_calibrate_tracks_accuracy(self):
        bp = BuildPredictor()
        # Predict low risk, build succeeds → correct
        bp.predict()
        bp.calibrate(build_succeeded=True)
        stats = bp.get_stats()
        assert stats["total_predictions"] == 1


class TestBuildPredictorStats:
    def test_initial_stats(self):
        bp = BuildPredictor()
        stats = bp.get_stats()
        assert stats["total_predictions"] == 0
        assert stats["accuracy"] == 0.0
        assert stats["build_history_length"] == 0

    def test_stats_after_predictions(self):
        bp = BuildPredictor()
        bp.predict(code_changes="test\n")
        bp.calibrate(build_succeeded=True)
        bp.predict(code_changes="test2\n")
        bp.calibrate(build_succeeded=False)

        stats = bp.get_stats()
        assert stats["total_predictions"] == 2
        assert stats["build_history_length"] == 2


class TestBuildPredictorReviewThreshold:
    def test_combined_high_risk_triggers_review(self):
        bp = BuildPredictor()
        # Seed failure history
        for _ in range(5):
            bp.calibrate(build_succeeded=False)

        # Large diff relative to total (>30%), many imports, many files
        import_lines = [f"+ import mod_{i}" for i in range(20)]
        filler_lines = [f"+ some_code_{i} = True" for i in range(100)]
        big_diff = "\n".join(import_lines + filler_lines)
        pred = bp.predict(
            code_changes=big_diff,
            changed_files_count=20,
            has_new_imports=True,
            total_lines=200,
        )
        assert pred.should_review is True
        assert pred.failure_probability >= REVIEW_THRESHOLD
