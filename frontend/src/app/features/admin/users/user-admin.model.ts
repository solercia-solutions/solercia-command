import { UserRole } from '../../../core/auth.service';

/** A user as returned by the admin endpoints (never includes the password). */
export interface AdminUser {
  id: string;
  email: string;
  primer_nombre: string;
  segundo_nombre?: string | null;
  primer_apellido: string;
  segundo_apellido?: string | null;
  full_name: string;
  dependency_id?: string | null;
  is_active: boolean;
  organization_id?: string;
  roles?: UserRole[];
  created_at?: string;
  updated_at?: string;
}

/** Backend list envelope: { data: [...], meta: { total } }. */
export interface AdminUserListResponse {
  data: AdminUser[];
  meta: { total: number };
}

/** Backend single-item envelope: { data: {...} }. */
export interface AdminUserItemResponse {
  data: AdminUser;
}

/** Payload for POST /admin/users (create). */
export interface CreateUserPayload {
  primer_nombre: string;
  segundo_nombre?: string | null;
  primer_apellido: string;
  segundo_apellido?: string | null;
  email: string;
  password: string;
  dependency_id?: string | null;
  is_active?: boolean;
  role_ids?: string[];
}

/** Payload for PATCH /admin/users/{id} (update — no password). */
export interface UpdateUserPayload {
  primer_nombre?: string;
  segundo_nombre?: string | null;
  primer_apellido?: string;
  segundo_apellido?: string | null;
  email?: string;
  dependency_id?: string | null;
  is_active?: boolean;
}

/** Body of PUT /admin/users/{id}/roles — replaces the user's role set. */
export interface UserRolesPayload {
  role_ids: string[];
}
