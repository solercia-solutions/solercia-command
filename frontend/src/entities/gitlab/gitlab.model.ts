/** Repositorio de GitLab que el token de la organización puede leer. */
export interface GitlabRepository {
  path_with_namespace: string;
  name: string;
  web_url: string | null;
}

/** Repositorios de GitLab vinculados a un proyecto de Command. */
export interface ProjectRepositories {
  project_id: string;
  repositories: string[];
}

export interface GitlabMergeRequest {
  repository: string;
  iid: number;
  title: string;
  state: string;
  author: string | null;
  source_branch: string | null;
  updated_at: string | null;
  web_url: string | null;
}

export interface GitlabCommit {
  repository: string;
  short_id: string;
  title: string;
  author_name: string | null;
  authored_at: string | null;
  web_url: string | null;
}

/**
 * Actividad de desarrollo de una tarea, leída en vivo. `connected=false`: la
 * organización no tiene GitLab conectado; `repositories` vacío: el proyecto no
 * tiene repositorios vinculados. Ambos son estados vacíos legítimos.
 */
export interface TaskDevelopmentActivity {
  connected: boolean;
  task_key: string | null;
  repositories: string[];
  merge_requests: GitlabMergeRequest[];
  commits: GitlabCommit[];
}
