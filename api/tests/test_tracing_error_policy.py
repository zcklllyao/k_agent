import unittest

from app.core.agent.tracing.error_policy import (
    is_non_fatal_infrastructure_error,
    is_non_fatal_loop_failure,
)


class TracingErrorPolicyTest(unittest.TestCase):
    def test_transient_upstream_errors_are_non_fatal(self) -> None:
        self.assertTrue(is_non_fatal_infrastructure_error("Connection error."))
        self.assertTrue(is_non_fatal_infrastructure_error(
        "Our servers are currently overloaded. Please try again later."
        ))
        self.assertTrue(is_non_fatal_infrastructure_error("HTTP 429: rate limit exceeded"))

    def test_auth_and_content_errors_remain_failures(self) -> None:
        self.assertFalse(is_non_fatal_infrastructure_error("API key is disabled"))
        self.assertFalse(is_non_fatal_infrastructure_error("invalid model name"))
        self.assertFalse(
            is_non_fatal_infrastructure_error("verifier returned no valid JSON object")
        )

    def test_loop_verifier_outage_is_non_fatal(self) -> None:
        self.assertTrue(
            is_non_fatal_loop_failure("verifier unavailable: incomplete chunked read")
        )

    def test_research_task_timeout_remains_a_real_loop_failure(self) -> None:
        self.assertFalse(
            is_non_fatal_loop_failure("research timed out after 900 seconds")
        )
        self.assertFalse(
            is_non_fatal_loop_failure("research task timed out; stale loop closed")
        )
