from session_sift.models import SavingsReport


def test_savings_report_console_format_contains_box_and_cost() -> None:
    report = SavingsReport(
        original_tokens=1000,
        refined_tokens=400,
        pass1_savings=200,
        pass2_savings=200,
        pass3_savings=200,
        elapsed_ms=12.5,
        turn=3,
    )

    output = report.to_console()

    assert "SESSION SIFT SAVINGS REPORT" in output
    assert "Cost saved" in output
    assert "┌" in output