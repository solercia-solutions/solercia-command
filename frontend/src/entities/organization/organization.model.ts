/** Role of a member within an organization (mirrors backend `MemberRole`). */
export type MemberRole = 'admin' | 'manager' | 'member' | 'viewer';

/** An organization (empresa/tenant). */
export interface Organization {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  created_at: string;
  created_by?: string | null;
  updated_by?: string | null;
}

/** One organization the caller belongs to, with their role in it — used by
 * "mis empresas" (`GET /organizations/mine`) and the org-switcher selector. */
export interface OrganizationMembership {
  organization: Organization;
  role: MemberRole;
}

/** A membership row enriched with the user's identity, for the members list. */
export interface OrganizationMember {
  id: string;
  organization_id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: MemberRole;
  created_at: string;
}

/** Backend list envelope: { data: [...] } (no `meta` on these endpoints). */
export interface OrganizationListResponse<T> {
  data: T[];
}

/** Backend single-item envelope: { data: {...}, message?: string }. */
export interface OrganizationItemResponse<T> {
  data: T;
  message?: string;
}

/** Payload to bootstrap a new organization. */
export interface OrganizationCreatePayload {
  name: string;
  slug: string;
}

/** Partial payload to update an organization. */
export interface OrganizationUpdatePayload {
  name?: string;
  slug?: string;
}

/** Payload to add an EXISTING user (found by email) as a member. */
export interface MemberCreatePayload {
  email: string;
  role: MemberRole;
}
