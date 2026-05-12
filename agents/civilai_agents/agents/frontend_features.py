from __future__ import annotations

from pathlib import Path

from ..base import BaseAgent
from ..models import CheckResult


class FrontendFeaturesAgent(BaseAgent):
    name = "frontend-features"
    description = "Static feature checks for auth, chat, account, subscription, upload, and saved-thread flows."

    def run(self) -> list[CheckResult]:
        return [
            self._check_auth_experience_modes(),
            self._check_protected_workspace_routes(),
            self._check_chat_api_integrations(),
            self._check_guest_mode_storage(),
            self._check_account_features(),
            self._check_subscription_features(),
            self._check_home_to_chat_intent(),
        ]

    @property
    def frontend_root(self) -> Path:
        return self.repo_root / "frontend" / "Website" / "civil-ai-web"

    def _read(self, relative_path: str) -> str:
        return (self.frontend_root / relative_path).read_text(encoding="utf-8", errors="replace")

    def _check_auth_experience_modes(self) -> CheckResult:
        auth_experience = self._read("app/components/AuthExperience.tsx")
        expected = ["initialMode", "login", "register", "continueAsGuest", "nextPath"]
        missing = [item for item in expected if item not in auth_experience]
        if missing:
            return self.fail_result(
                "auth-experience",
                "Auth experience is missing expected login/register/guest pieces.",
                missing=missing,
            )
        return self.pass_result(
            "auth-experience", "Login, register, guest mode, and redirect intent are represented."
        )

    def _check_protected_workspace_routes(self) -> CheckResult:
        protected_route = self._read("app/components/ProtectedRoute.tsx")
        routes = {
            "chat": self.frontend_root / "app" / "chat" / "page.tsx",
            "account": self.frontend_root / "app" / "account" / "page.tsx",
            "subscription": self.frontend_root / "app" / "subscription" / "page.tsx",
        }
        missing_routes = [name for name, path in routes.items() if not path.exists()]
        if "router.replace" not in protected_route or missing_routes:
            return self.fail_result(
                "protected-routes",
                "Protected workspace routing is incomplete.",
                missing_routes=missing_routes,
            )
        return self.pass_result(
            "protected-routes", "Protected route wrapper and workspace pages exist."
        )

    def _check_chat_api_integrations(self) -> CheckResult:
        chat_page = self._read("app/chat/page.tsx")
        expected = [
            "CUSTOM_API_BASE",
            "AUTH_API_BASE",
            "/jurisdictions",
            "/upload-pdf",
            "/ingestion-jobs/",
            "/query",
            "/chats",
            "Authorization",
        ]
        missing = [item for item in expected if item not in chat_page]
        if missing:
            return self.fail_result(
                "chat-integrations",
                "Chat workspace is missing expected backend integrations.",
                missing=missing,
            )
        return self.pass_result(
            "chat-integrations",
            "Chat workspace calls jurisdiction, query, upload, jobs, and saved-chat APIs.",
        )

    def _check_guest_mode_storage(self) -> CheckResult:
        auth_context = self._read("app/context/AuthContext.tsx")
        chat_page = self._read("app/chat/page.tsx")
        expected = [
            "GUEST_SESSION_KEY",
            "civilai_guest_threads_",
            "civilai_guest_active_thread_",
            "localStorage",
        ]
        combined = f"{auth_context}\n{chat_page}"
        missing = [item for item in expected if item not in combined]
        if missing:
            return self.warn_result(
                "guest-mode", "Guest mode persistence may be incomplete.", missing=missing
            )
        return self.pass_result(
            "guest-mode", "Guest session and guest chat persistence are represented."
        )

    def _check_account_features(self) -> CheckResult:
        account_page = self._read("app/account/page.tsx")
        expected = [
            "updateProfile",
            "CUSTOM_API_BASE",
            "/jurisdictions",
            "jurisdiction",
            "full_name",
        ]
        missing = [item for item in expected if item not in account_page]
        if missing:
            return self.fail_result(
                "account-features",
                "Account page is missing expected profile features.",
                missing=missing,
            )
        return self.pass_result(
            "account-features", "Account page supports profile refresh and updates."
        )

    def _check_subscription_features(self) -> CheckResult:
        subscription_page = self._read("app/subscription/page.tsx")
        expected = ["subscription", "usage"]
        missing = [item for item in expected if item not in subscription_page]
        if missing:
            return self.warn_result(
                "subscription-features",
                "Subscription page may be missing expected subscription display pieces.",
                missing=missing,
            )
        if "AUTH_API_BASE" not in subscription_page and "/subscription" not in subscription_page:
            return self.warn_result(
                "subscription-features",
                "Subscription page is present but appears static; add API-backed usage checks when billing is live.",
            )
        return self.pass_result(
            "subscription-features", "Subscription page includes subscription/usage integration."
        )

    def _check_home_to_chat_intent(self) -> CheckResult:
        home_page = self._read("app/page.tsx")
        chat_intent = self._read("app/lib/chatIntent.ts")
        expected = ["savePendingChatPrompt", "consumePendingChatPrompt", "sessionStorage"]
        combined = f"{home_page}\n{chat_intent}"
        missing = [item for item in expected if item not in combined]
        if missing:
            return self.warn_result(
                "home-chat-intent",
                "Home-to-chat prompt handoff may be incomplete.",
                missing=missing,
            )
        return self.pass_result(
            "home-chat-intent", "Home page prompt handoff into chat is represented."
        )
