# SPDX-License-Identifier: GPL-3.0-or-later
"""Addresses of the accounts module."""

from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from rentalars.accounts import ldap_views, views
from rentalars.accounts.forms import ResetPasswordForm

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("login/code/", views.login_code, name="login_code"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # AUT-004: reset the password through a link sent by e-mail.
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            form_class=ResetPasswordForm,
            template_name="accounts/password_reset.html",
            email_template_name="accounts/email/password_reset.txt",
            subject_template_name="accounts/email/password_reset_subject.txt",
            success_url=reverse_lazy("accounts:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/sent/",
        auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"),
        name="password_reset_done",
    ),
    # AUT-030: with the security log and the notice of the changed password.
    path("password-reset/<uidb64>/<token>/", views.PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path(
        "password-reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"),
        name="password_reset_complete",
    ),
    path("account/", views.account, name="account"),
    path("account/tokens/<int:pk>/revoke/", views.token_revoke, name="token_revoke"),
    path("account/two-factor/", views.two_factor_setup, name="two_factor_setup"),
    path("account/two-factor/off/", views.two_factor_disable, name="two_factor_disable"),
    path("account/sessions/", views.sessions, name="sessions"),
    path("account/new-password/", views.new_password, name="new_password"),
    path("administration/security-log/", views.security_log, name="security_log"),
    path("administration/users/<int:pk>/two-factor/reset/", views.user_reset_two_factor, name="user_reset_two_factor"),
    path("administration/users/", views.user_list, name="user_list"),
    path("administration/users/new/", views.user_create, name="user_create"),
    path("administration/users/<int:pk>/", views.user_edit, name="user_edit"),
    path("administration/users/<int:pk>/active/", views.user_set_active, name="user_set_active"),
    path("administration/users/<int:pk>/invite/", views.user_send_invitation, name="user_send_invitation"),
    path(
        "administration/users/<int:pk>/one-time-password/", views.user_one_time_password, name="user_one_time_password"
    ),
    # AUT-029: login with LDAP / Active Directory.
    path("administration/ldap/", ldap_views.ldap_settings, name="ldap_settings"),
    path("administration/ldap/test-connection/", ldap_views.ldap_test_connection, name="ldap_test_connection"),
    path("administration/ldap/test-login/", ldap_views.ldap_test_login, name="ldap_test_login"),
    path("administration/ldap/sync/", ldap_views.ldap_sync_accounts, name="ldap_sync"),
    path("administration/ldap/adopt/", ldap_views.ldap_adopt_dn, name="ldap_adopt_dn"),
    path("administration/ldap/assignments/new/", ldap_views.ldap_mapping_edit, name="ldap_mapping_create"),
    path("administration/ldap/assignments/<int:pk>/", ldap_views.ldap_mapping_edit, name="ldap_mapping_edit"),
    path(
        "administration/ldap/assignments/<int:pk>/delete/", ldap_views.ldap_mapping_delete, name="ldap_mapping_delete"
    ),
    path("administration/roles/", views.role_list, name="role_list"),
    path("administration/roles/new/", views.role_edit, name="role_create"),
    path("administration/roles/<int:pk>/", views.role_edit, name="role_edit"),
    path("administration/roles/<int:pk>/delete/", views.role_delete, name="role_delete"),
]
