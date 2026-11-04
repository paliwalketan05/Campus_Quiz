import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from fastapi import HTTPException

from app.main import create_app
from app.schemas.auth import AuthenticatedUser
from app.schemas.execution import AttemptResponseWrite, SessionCodeRequest
from app.services import execution_service

COLLEGE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
STUDENT_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
FACULTY_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
SESSION_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
ATTEMPT_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
QUESTION_ID = UUID("11111111-1111-4111-8111-111111111111")
OPTION_ID = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime.now(timezone.utc)


def make_student() -> AuthenticatedUser:
    return AuthenticatedUser(
        id=STUDENT_ID,
        college_id=COLLEGE_ID,
        email="student@example.edu",
        first_name="Quiz",
        last_name="Student",
        roles=["STUDENT"],
        must_change_password=False,
        token_version=1,
    )


def make_result(*, row=None, rows=None, scalar=None):
    result = MagicMock()
    result.mappings.return_value.one.return_value = row
    result.mappings.return_value.one_or_none.return_value = row
    result.mappings.return_value.all.return_value = rows or []
    result.scalar_one.return_value = scalar
    result.scalar_one_or_none.return_value = scalar
    return result


def attempt_row(*, status="IN_PROGRESS", deadline=None):
    return {
        "id": ATTEMPT_ID,
        "session_id": SESSION_ID,
        "student_user_id": STUDENT_ID,
        "status": status,
        "deadline": deadline or NOW + timedelta(minutes=10),
        "submitted_at": None,
        "finalized_at": None,
    }


class ExecutionSchemaTests(unittest.TestCase):
    def test_session_code_is_trimmed_and_normalized(self) -> None:
        self.assertEqual(
            SessionCodeRequest(session_code="  abc123  ").session_code,
            "ABC123",
        )

    def test_execution_routes_require_bearer_auth_and_hide_correctness(self) -> None:
        schema = create_app().openapi()
        paths = {
            "/api/v1/student/sessions",
            "/api/v1/student/sessions/join",
            "/api/v1/attempts/sessions/{session_id}/start",
            "/api/v1/attempts/{attempt_id}",
            "/api/v1/attempts/{attempt_id}/responses/{question_id}",
            "/api/v1/attempts/{attempt_id}/submit",
            "/api/v1/attempts/{attempt_id}/results",
            "/api/v1/sessions/{session_id}/analytics",
        }
        self.assertTrue(paths <= schema["paths"].keys())
        question_schema = schema["components"]["schemas"]["AttemptQuestionRead"]
        self.assertNotIn("is_correct", question_schema["properties"])
        self.assertNotIn("explanation", question_schema["properties"])
        for path in paths:
            for operation in schema["paths"][path].values():
                self.assertIn("security", operation)


class ExecutionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.connection = MagicMock()
        self.connection.execute = AsyncMock()
        self.connection.commit = AsyncMock()
        self.connection.rollback = AsyncMock()
        self.actor = make_student()
        self.settings = MagicMock()

    @patch("app.services.execution_service.create_actor_ticket", return_value="ticket")
    async def test_start_attempt_calls_procedure_with_student_role_ticket(
        self,
        create_ticket: MagicMock,
    ) -> None:
        self.connection.execute.return_value = make_result(
            row={
                "attempt_id": ATTEMPT_ID,
                "status": "IN_PROGRESS",
                "deadline": NOW + timedelta(minutes=10),
                "duration_minutes": 10,
                "snapshot_questions": [
                    {
                        "question_id": str(QUESTION_ID),
                        "question_text": "Safe question",
                        "options": [{"option_id": str(OPTION_ID), "option_text": "A"}],
                    }
                ],
            }
        )

        started = await execution_service.start_attempt(
            self.connection,
            self.actor,
            SESSION_ID,
            self.settings,
        )

        self.assertEqual(started["attempt_id"], ATTEMPT_ID)
        statement, parameters = self.connection.execute.await_args.args
        self.assertIn("sp_start_quiz_attempt", str(statement))
        self.assertEqual(parameters["auth_signature"], "ticket")
        create_ticket.assert_called_once_with(
            user_id=str(STUDENT_ID),
            token_version=1,
            role="STUDENT",
            settings=self.settings,
        )
        self.connection.commit.assert_awaited_once()

    async def test_lookup_session_is_scoped_to_college_and_enrollment(self) -> None:
        self.connection.execute.return_value = make_result(
            row={"id": SESSION_ID, "session_code": "ABC123"}
        )

        await execution_service.lookup_session(
            self.connection,
            self.actor,
            SessionCodeRequest(session_code="abc123"),
        )

        statement, parameters = self.connection.execute.await_args.args
        self.assertIn("student_enrollments", str(statement))
        self.assertIn("qs.college_id = :college_id", str(statement))
        self.assertEqual(parameters["college_id"], COLLEGE_ID)
        self.assertEqual(parameters["student_id"], STUDENT_ID)
        self.assertEqual(parameters["session_code"], "ABC123")

    async def test_attempt_state_selects_only_student_editable_response_columns(self) -> None:
        self.connection.execute.side_effect = [
            make_result(row=attempt_row()),
            make_result(
                rows=[
                    {
                        "question_id": QUESTION_ID,
                        "selected_option_ids": [OPTION_ID],
                        "is_marked_for_review": True,
                        "client_version": 2,
                        "client_submitted_at": NOW,
                        "server_received_at": NOW,
                    }
                ]
            ),
        ]

        state = await execution_service.get_attempt_state(
            self.connection,
            self.actor,
            ATTEMPT_ID,
        )

        response_select = str(self.connection.execute.await_args_list[1].args[0])
        self.assertNotIn("is_correct", response_select)
        self.assertNotIn("awarded_marks", response_select)
        self.assertEqual(state["responses"][0]["selected_option_ids"], [OPTION_ID])

    @patch("app.services.execution_service.create_actor_ticket", return_value="ticket")
    async def test_save_uses_response_procedure_and_preserves_retry_result(
        self,
        _ticket: MagicMock,
    ) -> None:
        self.connection.execute.side_effect = [
            make_result(row=attempt_row()),
            make_result(
                row={
                    "result_status": "IDEMPOTENT_RETRY",
                    "saved_version": 3,
                }
            ),
        ]
        payload = AttemptResponseWrite(
            selected_option_ids=[OPTION_ID],
            is_marked_for_review=True,
            client_version=3,
            client_submitted_at=NOW,
        )

        saved = await execution_service.save_response(
            self.connection,
            self.actor,
            ATTEMPT_ID,
            QUESTION_ID,
            payload,
            self.settings,
        )

        procedure_statement, parameters = self.connection.execute.await_args_list[1].args
        self.assertIn("sp_save_student_response", str(procedure_statement))
        self.assertEqual(parameters["selected_option_ids"], [OPTION_ID])
        self.assertEqual(saved["result_status"], "IDEMPOTENT_RETRY")
        self.connection.commit.assert_awaited_once()

    async def test_auto_finalize_is_rejected_before_deadline(self) -> None:
        self.connection.execute.return_value = make_result(
            row=attempt_row(deadline=NOW + timedelta(minutes=10))
        )

        with self.assertRaises(HTTPException) as raised:
            await execution_service.finalize_attempt(
                self.connection,
                self.actor,
                ATTEMPT_ID,
                "AUTO_TIME_EXPIRED",
                self.settings,
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(self.connection.execute.await_count, 2)
        self.assertNotIn(
            "sp_finalize_attempt",
            str(self.connection.execute.await_args_list[1].args[0]),
        )

    @patch("app.services.execution_service.create_actor_ticket", return_value="ticket")
    async def test_auto_finalize_requires_owned_expired_attempt(
        self,
        _ticket: MagicMock,
    ) -> None:
        self.connection.execute.side_effect = [
            make_result(row=attempt_row(deadline=NOW - timedelta(seconds=1))),
            make_result(scalar=True),
            make_result(
                row={
                    "final_status": "FINALIZED",
                    "total_score": Decimal("-1.00"),
                    "finalized_at": NOW,
                }
            ),
        ]

        finalized = await execution_service.finalize_attempt(
            self.connection,
            self.actor,
            ATTEMPT_ID,
            "AUTO_TIME_EXPIRED",
            self.settings,
        )

        procedure_statement, parameters = self.connection.execute.await_args_list[2].args
        self.assertIn("sp_finalize_attempt", str(procedure_statement))
        self.assertEqual(parameters["actor_id"], STUDENT_ID)
        self.assertEqual(finalized["total_score"], Decimal("-1.00"))
        self.connection.commit.assert_awaited_once()

    async def test_results_are_not_accessible_to_other_student(self) -> None:
        self.connection.execute.return_value = make_result(
            row={
                "student_user_id": OPTION_ID,
                "college_id": COLLEGE_ID,
                "faculty_user_id": FACULTY_ID,
            }
        )

        with self.assertRaises(HTTPException) as raised:
            await execution_service.get_attempt_results(
                self.connection,
                self.actor,
                ATTEMPT_ID,
                self.settings,
            )

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(self.connection.execute.await_count, 1)

    @patch("app.services.execution_service.create_actor_ticket", return_value="ticket")
    async def test_results_use_database_visibility_procedure(
        self,
        _ticket: MagicMock,
    ) -> None:
        self.connection.execute.side_effect = [
            make_result(
                row={
                    "student_user_id": STUDENT_ID,
                    "college_id": COLLEGE_ID,
                    "faculty_user_id": FACULTY_ID,
                }
            ),
            make_result(
                row={
                    "attempt_id": ATTEMPT_ID,
                    "status": "IN_PROGRESS",
                    "is_results_released": False,
                    "total_score": None,
                    "question_breakdown": None,
                }
            ),
        ]

        result = await execution_service.get_attempt_results(
            self.connection,
            self.actor,
            ATTEMPT_ID,
            self.settings,
        )

        statement = str(self.connection.execute.await_args_list[1].args[0])
        self.assertIn("sp_get_student_attempt_results", statement)
        self.assertFalse(result["is_results_released"])


if __name__ == "__main__":
    unittest.main()
