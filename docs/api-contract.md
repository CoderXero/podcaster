# Gumu-Gumu API contract checklist

The supplied specification does not establish a verified live contract. Before enabling publication, confirm:

1. HTTPS API base URL, IdP client-credentials grant, audience/scope, roles, and token errors.
2. `POST /api/v1/episodes` response ID field, draft state, validation limits, lookup by `local_episode_id`, and idempotency behavior.
3. `POST /api/v1/episodes/{id}/publish` status code, asynchronous behavior, and the official `GET` state response.
4. Whether the backend can read private Azure blobs, accepted URI form, upload permissions, limits, retention, and mandatory artwork.
5. Allowed title/metadata lengths and topics/tags vocabularies.

The implementation refuses to publish unless a validated remote storage adapter is selected. `file://` URIs and guessed public Blob URLs are never accepted.
