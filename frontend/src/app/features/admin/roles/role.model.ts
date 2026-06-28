/** An RBAC role, organization-scoped. */
export interface Role {
  id: string;
  organization_id: string;
  code: string;
  name: string;
  is_active: boolean;
  /** When present (e.g. on GET /admin/roles/{id}), the role's menu ids. */
  menu_ids?: string[];
  created_at?: string;
  updated_at?: string;
}

/** Backend list envelope: { data: [...], meta: { total } }. */
export interface RoleListResponse {
  data: Role[];
  meta: { total: number };
}

/** Backend single-item envelope: { data: {...} }. */
export interface RoleItemResponse {
  data: Role;
}

/** Payload for creating/updating a role. */
export interface RolePayload {
  code: string;
  name: string;
  is_active?: boolean;
}

/** Body of PUT /admin/roles/{id}/menus — replaces the role's menu set. */
export interface RoleMenusPayload {
  menu_ids: string[];
}
