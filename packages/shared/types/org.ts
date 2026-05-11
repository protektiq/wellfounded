/**
 * Shared types for organization and user API payloads.
 * Keep aligned with apps/api/orgs/schemas.py.
 */

export type UserRole = "admin" | "attorney" | "paralegal" | "student";

export type UserStatus = "invited" | "active" | "suspended";

export interface OrganizationCreate {
  name: string;
  slug: string;
}

export interface OrganizationRead {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  deleted_at: string | null;
  kms_data_key_arn: string | null;
}

export interface UserCreate {
  email: string;
  display_name: string;
  role: UserRole;
  status: UserStatus;
}

export interface UserRead {
  id: string;
  organization_id: string;
  email: string;
  display_name: string;
  role: UserRole;
  status: UserStatus;
  created_at: string;
  last_login_at: string | null;
  deleted_at: string | null;
}

export interface UserListItem {
  id: string;
  organization_id: string;
  email: string;
  display_name: string;
  role: UserRole;
  status: UserStatus;
  created_at: string;
}
