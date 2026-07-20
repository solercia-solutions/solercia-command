/** Domain types for organizational role templates ("Equipos" onboarding). */
import { Methodology } from '@entities/project/project.model';

/** List item of `GET /org-role-templates` (no tree). */
export interface OrgRoleTemplate {
  id: string;
  name: string;
  is_system: boolean;
}

/** A node of the template tree, nested with its children. */
export interface OrgRoleTemplateNode {
  id: string;
  name: string;
  default_methodology: Methodology;
  children: OrgRoleTemplateNode[];
}

/** Detail of `GET /org-role-templates/:id` — includes the full node tree. */
export interface OrgRoleTemplateDetail extends OrgRoleTemplate {
  tree: OrgRoleTemplateNode;
}

/** One project generated (or reconciled) by an instantiation. */
export interface InstantiatedProject {
  id: string;
  name: string;
  methodology: Methodology;
  parent_project_id: string | null;
  lead_user_id: string | null;
}

export interface OrgRoleTemplateListResponse {
  data: OrgRoleTemplate[];
}

export interface OrgRoleTemplateDetailResponse {
  data: OrgRoleTemplateDetail;
}

export interface InstantiateResponse {
  data: InstantiatedProject[];
}
