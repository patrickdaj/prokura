# human-approval — delta (add-authority-console / M8)

## ADDED Requirements

### Requirement: User-bound read APIs for the authority console
The approval service SHALL expose read-only APIs authenticated by a user-bound
bearer token (verified signature and approval-service audience): the token
subject's pending and recent approvals, and the token subject's notification
topic. These APIs SHALL derive the user exclusively from the verified token,
SHALL expose no other user's data, and SHALL NOT accept decisions — approve/deny
remains exclusively on the approval surface's own authenticated session.

#### Scenario: Console lists the subject's approvals
- **WHEN** a bearer for user U with the approval-service audience calls the
  approvals read API
- **THEN** only U's approvals are returned, each linking to the approval surface
  for any decision

#### Scenario: Read API cannot decide
- **WHEN** any request authenticated by a bearer token attempts to approve or
  deny an approval
- **THEN** it is refused — the decision endpoints accept only the approval
  surface's session

#### Scenario: Topic is served only to its owner
- **WHEN** a bearer for user U requests the notification topic
- **THEN** the response is U's topic only, and a wrong-audience or invalid token
  is refused before any derivation
