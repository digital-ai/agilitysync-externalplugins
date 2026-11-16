# GitHub Integration for Digital.ai Agility Sync

This document describes what the GitHub integration supports, what it does not support, and the known limitations. It is intended for customers and administrators setting up a sync between GitHub and Digital.ai Agility.

---

## 1. Overview

The GitHub integration keeps GitHub issues and Digital.ai Agility work items in sync. It works with:

- **GitHub repositories** – issues in one or more repositories of a GitHub organization.
- **GitHub Projects** (the newer "Projects" boards) – optionally, a mapping can be tied to one GitHub Project so that its custom fields are synced too.
- **GitHub issue types** – such as Bug, Feature, Task or Story, as defined by your GitHub organization.

Sync can run in either direction (GitHub → Agility, Agility → GitHub) or both.

---

## 2. Setting up a connection

When adding a GitHub instance you provide:

| Setting | What to enter |
|---|---|
| Name | Any name to identify this connection |
| Username | The GitHub username of the sync user (the account that owns the token) |
| API Token | A GitHub personal access token for that user |
| URL | The GitHub web address: `https://github.com`, or your GitHub Enterprise Server address. Agility Sync works out the API address itself. Connections that still use `https://api.github.com` keep syncing, but their work item links in the sync logs open the API instead of the issue page. |
| Organization | The GitHub organization login (one organization per connection) |

### Token permissions

The token must belong to a user who has access to the organization and its repositories, and should include:

- Access to repositories and their issues (read and write)
- Access to organization webhooks (needed when a GitHub Project is used – this usually requires an organization owner)
- Access to repository webhooks (needed when no GitHub Project is used)
- Access to GitHub Projects (read and write)
- Read access to organization information (needed to list issue types and issue fields)

> Changes made by the sync user in GitHub are recognised as coming from Agility Sync and are not synced back, which prevents loops. For this reason, use a dedicated account as the sync user and avoid making manual changes with that account.

---

## 3. Creating a mapping

A mapping is configured in three steps on the GitHub side:

1. **GitHub Project** – choose a GitHub Project, or choose **No Project** for a repository-only mapping.
2. **Repositories** – choose up to 10 repositories.
3. **Issue Types** – choose the GitHub issue type to sync.
   - With a GitHub Project selected, all of your organization's issue types are offered, plus a general **Issue** type for issues that have no type.
   - With **No Project**, only the general **Issue** type is offered, and it covers all issues in the repository.

### Webhooks

Agility Sync creates the GitHub webhook automatically when a mapping is activated:

- **With a GitHub Project:** an organization-level webhook is created (requires organization owner rights for the token).
- **With No Project:** a webhook is created on each selected repository.

Webhooks can also be set up manually if your organization does not allow automatic creation.

> If you change the GitHub Project on an existing mapping, re-select the repositories and save the mapping again so that the correct webhook is used.

---

## 4. What is supported

### 4.1 Work items

| Action | GitHub → Agility | Agility → GitHub |
|---|---|---|
| Create | Yes | Yes |
| Update | Yes | Yes |
| Close / Delete | Closing an issue in GitHub is treated as a delete in Agility | Deleting an item in Agility closes the GitHub issue (as "not planned") |
| Reopen | Not supported | Not supported |

- Issues created in GitHub with an issue type are created **once** in Agility, even though GitHub sends more than one notification for a new issue.
- If an issue's type is set after the issue was created, the issue is created in Agility at that point.
- Issues that existed before the mapping was activated are created in Agility the next time they are changed in GitHub. GitHub Project field values are not included in that first create; they sync on their next change.
- New issues created in GitHub from Agility are automatically added to the GitHub Project selected in the mapping.
- Once an issue is closed, further changes to it (including GitHub Project automation such as "Item closed → Done") are not synced, so a closed or deleted item is never re-created in Agility.

### 4.2 Fields

| GitHub field | Supported | Notes |
|---|---|---|
| Title | Yes, both directions | Required |
| Description | Yes, both directions | Formatting is converted between GitHub (Markdown) and Agility (rich text). See limitations. |
| Assignee | Yes, both directions | Shown as a user field. Users are matched by name: the GitHub username must be the same as the Agility member's username. Members that cannot be matched are skipped. |
| Labels | Yes, both directions | Shown as a multi-select list of the repository's labels. Use value mapping to match Agility values to label names. |
| Milestone | Yes, both directions | Single-select list of the repository's open milestones. Use value mapping to match Agility values to milestone names. |
| GitHub Project fields | Yes, both directions | Available when a GitHub Project is selected. Supports text, number, date, single select and iteration fields. |
| GitHub Issue Fields (organization custom fields) | Yes, both directions | Supports text, number, date, single select and multi select fields. Text issue fields can also be used for Sync Reference. |

**GitHub Project fields**

- Changes made to a mapped Project field in GitHub are synced to Agility.
- Changes made in Agility are written to the issue's Project field in GitHub.
- Changes to Project fields that are **not** mapped are ignored. This includes changes made automatically by GitHub's own Project automation (for example, GitHub setting Status to "Todo" when an issue is added to a Project).
- For single select and iteration fields, the option names in the value mapping must exactly match the option names in GitHub.
- GitHub also shows your organization's Issue Fields (such as Priority, Start date and Target date) inside each Project. These are listed only once in the field mapping, as Issue Fields.

### 4.3 Comments

- Comments are synced in both directions.

### 4.4 Parent / child relationships

- GitHub sub-issues are synced as parent/child relationships in Agility, and vice versa.
- Both the parent and the child must already be synced, and both must be in the same repository.
- The relationship must be valid in Agility. For example, in Agility a Story's parent must be an Epic. Map GitHub issue types to the matching Agility asset types, for example:

| GitHub issue type | Agility asset type |
|---|---|
| Feature | Epic |
| Story / Bug | Story / Defect |
| Task | Task |

### 4.5 Sync Reference

After an item is created, Agility Sync can record the ID and URL of the item in the other system.

- **In Agility:** select Agility custom text fields to hold the GitHub issue number and GitHub issue link. If no fields are selected, a link to the GitHub issue is added to the Agility item.
- **In GitHub:** select GitHub Project text fields or GitHub Issue Fields (text) to hold the Agility ID and link. If no fields are selected, a comment such as "Synced with Digital.ai Agility B-01234" with a link is added to the GitHub issue.
- Sync Reference is written only when an item is first created. Items created before Sync Reference was configured are not updated.

### 4.6 Other options

- **Sync selected event types** – choose to sync only creates, only updates, and so on.
- **Conflict resolution** – supported.

---

## 5. What is not supported

| Feature | Status |
|---|---|
| Attachments (files and images) | Not supported in either direction. Images embedded in descriptions or comments are not copied. |
| Pull requests | Not synced. |
| Commits | Not synced by Agility Sync. Use Agility's **CommitStream** integration to show GitHub commits on Agility work items (include the Agility number, such as S-01234, in the commit message). |
| Links (URLs) | Not supported as a separate option. Use Sync Reference to link the two items. |
| Dependencies (blocked by / blocking) | Not supported. |
| Goals | Not supported. |
| GitHub Project reports / Insights charts | Not available from GitHub. Map the underlying fields (such as Status, Iteration and Estimate) to Agility fields so that Agility's own reports reflect the GitHub work. |
| Reopening an issue | Not synced. |
| Draft items in GitHub Projects | Not synced. Only issues are supported. |
| Data migration (bulk sync of existing items) | Not supported. |
| Recovery of missed events | Not supported. If Agility Sync is unavailable when a change is made, that change is not picked up later. |
| Multiple organizations in one connection | Not supported. Create one connection per GitHub organization. |

---

## 6. Known limitations

1. **Description formatting** – GitHub uses Markdown and Agility uses rich text. Text is converted in both directions, but some formatting (spacing, list styles, tables) may look slightly different after sync. Images in descriptions are not synced.
2. **Milestones** – only open milestones are listed and can be set from Agility. Setting a closed milestone from Agility fails with a "does not exist" error.
3. **Assignees** – the Agility member's username must be the same as the GitHub username. Users who are not members of the repository cannot be assigned in GitHub.
4. **Labels** – only the first 100 labels of a repository are shown. Labels are listed per repository.
5. **Repositories per mapping** – up to 10 repositories.
6. **Relationships** – parent and child must be in the same repository, and the relationship must be allowed by Agility's hierarchy.
7. **Overlapping mappings** – do not create more than one active mapping that syncs the same repository and issue type into the same Agility instance. Overlapping mappings can create duplicate items and incorrect parent links.
8. **Comments** – editing a comment may post it again as a new comment. Deleting a comment is not synced.
9. **Sync Reference** – only written when an item is first created.
10. **GitHub Project field changes** – each change made directly on a GitHub Project board is looked up in GitHub before it is synced, so very large bulk edits on a board can take longer and use more of GitHub's API allowance.
11. **Existing mappings after an upgrade** – if fields such as Description, Labels, Milestone or Project fields are not shown or behave as text, open the mapping, remove the field row, select the field again, and save the mapping.
12. **Organization features** – issue types and Issue Fields must be enabled in your GitHub organization to be used.
13. **Fields with the same name** – if a GitHub Project field has the same name as an organization Issue Field, only the Issue Field is listed in the field mapping and the Project field cannot be mapped. To map such a Project field, give it a different name in the GitHub Project.

---

## 7. Best practices

- Use a dedicated GitHub account as the sync user.
- Keep one mapping per repository and issue type for each Agility instance.
- Match GitHub issue types to the equivalent Agility asset types so that parent/child links are valid.
- Set up user/value mapping for assignees, labels, and single select fields.
- After changing a mapping, save and activate it again so that the webhook is updated.
