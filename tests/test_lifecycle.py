import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from fastapi import HTTPException

from app.main import create_app
from app.schemas.auth import AuthenticatedUser
from app.schemas.lifecycle import QuizSessionCreate
from app.services import lifecycle_service

COLLEGE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
FACULTY_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
QUIZ_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
CLASS_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
SESSION_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
SUBJECT_ID = UUID("11111111-1111-4111-8111-111111111111")
NOW = datetime.now(timezone.utc)


def make_faculty() -> AuthenticatedUser:
    return AuthenticatedUser(
        id=FACULTY_ID,
        college_id=COLLEGE_ID,
        email="faculty@example.edu",
        first_name="Quiz",
        last_name="Faculty",
        roles=["FACULTY"],
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


def quiz_row(*, status="PUBLISHED"):
    return {
        "id": QUIZ_ID,
        "college_id": COLLEGE_ID,
        "faculty_user_id": FACULTY_ID,
        "subject_id": SUBJECT_ID,
        "status": status,
        "default_duration_minutes": 25,
        "default_result_visibility": "AFTER_SESSION_ENDS",
    }


def session_row(*, status="SCHEDULED"):
    return {
        "id": SESSION_ID,
        "college_id": COLLEGE_ID,
        "quiz_id": QUIZ_ID,
        "faculty_user_id": FACULTY_ID,
        "class_id": CLASS_ID,
        "session_code": "ABCDEFG2",
        "session_mode": "STUDENT_PACED",
        "status": status,
        "start_window_time": NOW,
        "end_window_time": NOW + timedelta(hours=1),
        "actual_started_at": None,
        "actual_ended_at": None,
        "duration_minutes": 25,
        "negative_marking_enabled": None,
        "negative_penalty": None,
        "result_visibility": "AFTER_SESSION_ENDS",
        "results_released_at": None,
        "created_at": NOW,
        "updated_at": NOW,
    }


class LifecycleSchemaTests(unittest.TestCase):
    def test_session_window_requires_timezone(self) -> None:
        with self.assertRaises(ValueError):
            QuizSessionCreate(
                quiz_id=QUIZ_ID,
                class_id=CLASS_ID,
                start_window_time=datetime(2026, 11, 3, 10),
                end_window_time=datetime(2026, 11, 3, 11),
            )

    def test_session_window_requires_end_after_start(self) -> None:
        with self.assertRaises(ValueError):
            QuizSessionCreate(
                quiz_id=QUIZ_ID,
                class_id=CLASS_ID,
                start_window_time=NOW,
                end_window_time=NOW,
            )

    def test_lifecycle_routes_require_bearer_auth_and_do_not_define_snapshot(self) -> None:
        openapi = create_app().openapi()
        expected_paths = {
            "/api/v1/quizzes/{quiz_id}/publish",
            "/api/v1/sessions",
            "/api/v1/sessions/{session_id}",
            "/api/v1/sessions/{session_id}/release-results",
            "/api/v1/sessions/{session_id}/{action}",
        }
        self.assertTrue(expected_paths <= openapi["paths"].keys())
        self.assertNotIn(
            "snapshot_json",
            openapi["components"]["schemas"]["QuizSessionRead"]["properties"],
        )
        for path in expected_paths:
            for operation in openapi["paths"][path].values():
                self.assertIn("security", operation)


class LifecycleServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.connection = MagicMock()
        self.connection.execute = AsyncMock()
        self.connection.commit = AsyncMock()
        self.connection.rollback = AsyncMock()
        self.actor = make_faculty()
        self.settings = MagicMock()

    @patch("app.services.lifecycle_service.create_actor_ticket", return_value="ticket")
    @patch("app.services.lifecycle_service.authoring_service.get_quiz", new_callable=AsyncMock)
    async def test_publish_calls_procedure_and_commits(
        self,
        get_quiz: AsyncMock,
        _ticket: MagicMock,
    ) -> None:
        get_quiz.return_value = quiz_row()
        procedure_result = {
            "quiz_id": QUIZ_ID,
            "status": "PUBLISHED",
            "total_marks": Decimal("12.50"),
        }
        self.connection.execute.side_effect = [
            make_result(scalar=1),
            make_result(row=procedure_result),
        ]

        published = await lifecycle_service.publish_quiz(
            self.connection,
            self.actor,
            QUIZ_ID,
            self.settings,
        )

        self.assertEqual(published["total_marks"], Decimal("12.50"))
        self.assertIn("sp_publish_quiz", str(self.connection.execute.await_args_list[1].args[0]))
        self.connection.commit.assert_awaited_once()

    @patch("app.services.lifecycle_service._new_session_code", return_value="ABCDEFG2")
    @patch("app.services.lifecycle_service.authoring_service.get_quiz", new_callable=AsyncMock)
    async def test_create_session_uses_quiz_defaults_and_assignment(
        self,
        get_quiz: AsyncMock,
        _session_code: MagicMock,
    ) -> None:
        get_quiz.return_value = quiz_row()
        self.connection.execute.side_effect = [
            make_result(scalar=1),
            make_result(scalar=SESSION_ID),
            make_result(row=session_row()),
        ]
        request = QuizSessionCreate(
            quiz_id=QUIZ_ID,
            class_id=CLASS_ID,
            start_window_time=NOW,
            end_window_time=NOW + timedelta(hours=1),
        )

        created = await lifecycle_service.create_session(
            self.connection,
            self.actor,
            request,
        )

        self.assertEqual(created["session_code"], "ABCDEFG2")
        insert_parameters = self.connection.execute.await_args_list[1].args[1]
        self.assertEqual(insert_parameters["duration_minutes"], 25)
        self.assertEqual(insert_parameters["result_visibility"], "AFTER_SESSION_ENDS")
        self.assertEqual(insert_parameters["faculty_user_id"], FACULTY_ID)
        self.assertNotIn("snapshot_json", created)
        self.connection.commit.assert_awaited_once()

    @patch("app.services.lifecycle_service.create_actor_ticket", return_value="ticket")
    async def test_transition_uses_procedure_and_returns_only_sanitized_session(
        self,
        _ticket: MagicMock,
    ) -> None:
        self.connection.execute.side_effect = [
            make_result(row=session_row()),
            make_result(scalar="ACTIVE"),
            make_result(row=session_row(status="ACTIVE")),
        ]

        updated = await lifecycle_service.transition_session(
            self.connection,
            self.actor,
            SESSION_ID,
            "activate",
            self.settings,
        )

        procedure_statement = str(self.connection.execute.await_args_list[1].args[0])
        self.assertIn("sp_activate_quiz_session", procedure_statement)
        self.assertEqual(updated["status"], "ACTIVE")
        self.assertNotIn("snapshot_json", updated)
        self.assertNotIn("is_correct", updated)
        self.connection.commit.assert_awaited_once()

    @patch("app.services.lifecycle_service.create_actor_ticket", return_value="ticket")
    async def test_release_results_uses_authorized_procedure(
        self,
        _ticket: MagicMock,
    ) -> None:
        self.connection.execute.side_effect = [
            make_result(row=session_row(status="COMPLETED")),
            make_result(scalar=NOW),
            make_result(row={**session_row(status="COMPLETED"), "results_released_at": NOW}),
        ]

        updated = await lifecycle_service.release_session_results(
            self.connection,
            self.actor,
            SESSION_ID,
            self.settings,
        )

        statement = str(self.connection.execute.await_args_list[1].args[0])
        self.assertIn("sp_release_session_results", statement)
        self.assertEqual(updated["results_released_at"], NOW)
        self.connection.commit.assert_awaited_once()

    @patch("app.services.lifecycle_service.authoring_service.get_quiz", new_callable=AsyncMock)
    async def test_only_published_quiz_can_be_scheduled(self, get_quiz: AsyncMock) -> None:
        get_quiz.return_value = quiz_row(status="DRAFT")
        request = QuizSessionCreate(
            quiz_id=QUIZ_ID,
            class_id=CLASS_ID,
            start_window_time=NOW,
            end_window_time=NOW + timedelta(hours=1),
        )

        with self.assertRaises(HTTPException) as raised:
            await lifecycle_service.create_session(
                self.connection,
                self.actor,
                request,
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.connection.commit.assert_not_awaited()

    async def test_session_reads_are_scoped_to_faculty_owner(self) -> None:
        self.connection.execute.return_value = make_result(row=session_row())

        await lifecycle_service.get_session(
            self.connection,
            self.actor,
            SESSION_ID,
        )

        statement, parameters = self.connection.execute.await_args.args
        self.assertIn("faculty_user_id = :actor_id", str(statement))
        self.assertEqual(parameters["college_id"], COLLEGE_ID)
        self.assertEqual(parameters["actor_id"], FACULTY_ID)


if __name__ == "__main__":
    unittest.main()
