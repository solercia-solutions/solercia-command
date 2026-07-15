/** An organization-scoped dependency ("dependencia" / área). */
export interface Dependency {
  id: string;
  organization_id: string;
  name: string;
  code?: string | null;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

/** Backend list envelope: { data: [...], meta: { total } }. */
export interface DependencyListResponse {
  data: Dependency[];
  meta: { total: number };
}

/** Backend single-item envelope: { data: {...} }. */
export interface DependencyItemResponse {
  data: Dependency;
}

/** Payload for creating/updating a dependency. */
export interface DependencyPayload {
  name: string;
  code?: string | null;
  is_active?: boolean;
}
