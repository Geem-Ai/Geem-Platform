# Geem Workspace Flutter

Flutter client for the **Geem Workspace chat experience** on Android and iOS.
It reuses the production Workspace API and follows the visual language of
`apps/workspace_web`, including Arabic-first RTL support, English, the Geem
brand palette, system light/dark themes, and the vendored Geem assistant avatar.

## Current scope

The app currently provides:

- Login, forgot password, password reset, email verification, and resend
  verification flows.
- Secure session restore, refresh-token rotation, and logout.
- Workspace selection with a remembered workspace per user.
- New text chats with an Expert, defaulting to Geem General when available.
- Persisted chat history, pinned and recent sections, and a favorites filter.
- Favorite/unfavorite, pin/unpin, rename, and delete conversation actions.
- Streaming GFM Markdown answers, generation status, stop, retry, citations,
  safe external links, and asynchronously generated conversation titles.
- Responsive desktop/tablet shell and mobile drawer without sample prompts.

This is intentionally a **text-chat-only** client. It does not currently
include file attachments, voice recording/transcription, push notifications,
offline synchronization, sample prompt chips, registration, workspace
administration, Expert administration, billing, storage, members, or apps.
Those remain available in `apps/workspace_web` where applicable.

## Requirements

- Flutter 3.44 or newer
- Dart 3.12 or newer
- Xcode and CocoaPods for iOS builds
- Android SDK for Android builds
- A reachable Geem API with an existing user and Workspace

From the repository root:

```bash
cd apps/workspace_flutter
flutter pub get
```

## API configuration

The API base URL is a compile-time Dart define named `GEEM_API_URL`. It must be
an absolute HTTP(S) URL and should not have a trailing slash.

Run against UAT:

```bash
flutter run --dart-define=GEEM_API_URL=https://api-uat.geem.ai
```

Run against production:

```bash
flutter run --dart-define=GEEM_API_URL=https://api.geem.ai
```

If the define is omitted, the app safely defaults to the production API at
`https://api.geem.ai`. For local development, `localhost` inside an Android
emulator refers to the emulator itself, so use the Android emulator host alias
for a host-run API:

```bash
flutter run -d <android-device-id> \
  --dart-define=GEEM_API_URL=http://10.0.2.2:8000
```

Android debug builds allow cleartext HTTP for local development. Release
builds should use HTTPS. An iOS simulator can normally reach the Mac through
`localhost`/`127.0.0.1`; physical devices must use a reachable LAN address or
an HTTPS environment such as UAT.

The value is compiled into the app. Pass the appropriate define again for
every release build; this app does not read the Workspace Web `.env` file.

## Existing API contract

No backend route or schema was added for this client. It uses the same APIs as
`apps/workspace_web`, including:

- `/api/auth/*` for login, refresh, logout, password reset, and verification.
- `/api/auth/me` for the user and available Workspaces.
- `/api/experts` for the chat Expert picker.
- `/api/conversations` and its message endpoints for history and mutations.
- `/api/conversations/{id}/messages/stream` for POST-based SSE chat streaming.
- `/api/conversations/{id}/messages/{message_id}/retry/stream` for retry.

Authenticated requests send `Authorization: Bearer ...`. Workspace-scoped
requests also send `X-Workspace-Id`. Workspace switching is client-side and
does not require a new API endpoint.

## Session security and rotation

The backend returns short-lived access tokens in JSON and a rotating
`geem_refresh` token in the `Set-Cookie` header. Native clients can read the
response header even though the cookie is marked `HttpOnly` for browser
security.

The Flutter client:

1. Keeps the access token in memory only.
2. Extracts `geem_refresh` after login, verification, reset, and refresh.
3. Stores the refresh token using `flutter_secure_storage` (Keychain on iOS and
   encrypted Keystore-backed storage on Android).
4. Sends the stored token in the supported `/api/auth/refresh` JSON body.
5. Replaces the stored token after every rotation.
6. Serializes concurrent refresh attempts into a single in-flight request so
   rotating tokens cannot race and revoke the session family.
7. Deletes the local token during logout even if the network request fails.

The selected Workspace and locale are also persisted through the secure
credential store. Android application backup is disabled so encrypted storage
is not restored without its device key.

## Password-reset and verification links

The app understands full links or raw tokens for both flows. Supported app
links include:

```text
https://hub.geem.ai/verify-email?token=...
https://hub.geem.ai/reset-password?token=...
https://app-uat.geem.ai/verify-email?token=...
https://app-uat.geem.ai/reset-password?token=...
geem://auth/verify-email?token=...
geem://auth/reset-password?token=...
```

The custom `geem://` scheme is registered in both mobile projects. The backend
currently generates HTTPS email links from `WORKSPACE_WEB_URL`, which gives a
safe web fallback.

For HTTPS links to open the installed app automatically, deployment must also:

- Serve `/.well-known/assetlinks.json` on each Android link host with package
  name `ai.geem.workspace` and the release signing-certificate SHA-256 digest.
- Serve `/.well-known/apple-app-site-association` on each iOS link host with
  the Apple Team ID and app ID `ai.geem.workspace`.
- Provision the iOS App ID/profile for the `applinks:hub.geem.ai` and
  `applinks:app-uat.geem.ai` entries already present in Runner entitlements.
- Serve both association files directly over HTTPS without a redirect.

Until those association files and the matching iOS capability are deployed,
the HTTPS link opens the existing Workspace Web verification/reset page. Users
can also choose the app's verification/reset link action and paste either the
complete email link or its raw token.

## Application identity

The Android application ID/namespace and iOS bundle ID are:

```text
ai.geem.workspace
```

Keep this identifier aligned with signing, store records, and the HTTPS
association files.

## Tests and static analysis

```bash
cd apps/workspace_flutter
flutter analyze
flutter test
```

The test suite covers API model parsing, backend-ready Expert selection,
Workspace chat permission, login/reset UI, hidden reset credentials, trusted
deep links, transient and terminal session restore failures, refresh-token
rotation/single-flight behavior, late concurrent 401s, logout during rotation,
and chunked/CRLF/multiline SSE parsing.

## Branding assets

Both platform launcher icon sets are generated from the vendored Geem mascot.
After changing `assets/brand/geem-app-icon.png`, regenerate them with:

```bash
dart run tool/generate_app_icon.dart
dart run flutter_launcher_icons
```

## Builds

Android debug APK against a local host-run API:

```bash
flutter build apk --debug \
  --dart-define=GEEM_API_URL=http://10.0.2.2:8000
```

Android release bundle:

```bash
flutter build appbundle --release \
  --dart-define=GEEM_API_URL=https://api.geem.ai
```

Local release builds fall back to Android's debug signing key. Store or CI
builds must copy `android/key.properties.example` to the ignored
`android/key.properties`, provide the upload-keystore values, and use that
release certificate's SHA-256 digest in each host's `assetlinks.json`.

iOS release archive (requires signing configured in Xcode):

```bash
flutter build ipa --release \
  --dart-define=GEEM_API_URL=https://api.geem.ai
```

For a simulator-only iOS build:

```bash
flutter build ios --simulator \
  --dart-define=GEEM_API_URL=http://localhost:8000
```
