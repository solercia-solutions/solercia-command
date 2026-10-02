import { Routes } from '@angular/router';
import { authGuard } from '@features/auth/auth.guard';

export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () =>
      import('@pages/login/login.component').then((m) => m.LoginComponent),
  },
  {
    // No authGuard: the browser lands here straight from the backend's SSO
    // callback redirect, before any access token exists yet (design.md D5).
    path: 'auth/callback',
    loadComponent: () =>
      import('@pages/auth-callback/auth-callback.component').then(
        (m) => m.AuthCallbackComponent,
      ),
  },
  // Error pages, siblings of 'login' and outside authGuard on purpose: a 401
  // must not require a session to be seen. One component parameterised by
  // `data.code` — see error-page.component.ts.
  {
    path: 'no-autorizado',
    loadComponent: () =>
      import('@pages/errors/error-page.component').then(
        (m) => m.ErrorPageComponent,
      ),
    data: { code: 401 },
  },
  {
    path: 'prohibido',
    loadComponent: () =>
      import('@pages/errors/error-page.component').then(
        (m) => m.ErrorPageComponent,
      ),
    data: { code: 403 },
  },
  {
    path: 'error-servidor',
    loadComponent: () =>
      import('@pages/errors/error-page.component').then(
        (m) => m.ErrorPageComponent,
      ),
    data: { code: 500 },
  },
  {
    // Authenticated layout (header, sidebar, session actions): parent of every
    // view that requires a session. The guard runs on entering the shell and
    // again on every child navigation, as it did when each route carried it.
    path: '',
    loadComponent: () =>
      import('@pages/shell').then((m) => m.ShellPageComponent),
    canActivate: [authGuard],
    canActivateChild: [authGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'projects' },
      {
        path: 'tasks/import',
        loadComponent: () =>
          import('@pages/task-import/task-import-preview.component').then(
            (m) => m.TaskImportPreviewComponent,
          ),
      },
      {
        path: 'projects',
        loadComponent: () =>
          import('@pages/projects/projects.component').then(
            (m) => m.ProjectsComponent,
          ),
      },
      {
        path: 'projects/:id',
        loadComponent: () =>
          import(
            '@widgets/project-workspace/project-workspace.component'
          ).then((m) => m.ProjectWorkspaceComponent),
      },
      {
        path: 'hierarchy',
        loadComponent: () =>
          import('@pages/hierarchy/hierarchy.component').then(
            (m) => m.HierarchyComponent,
          ),
      },
      {
        path: 'executive',
        loadComponent: () =>
          import('@pages/executive/executive.component').then(
            (m) => m.ExecutiveComponent,
          ),
      },
      {
        path: 'performance',
        loadComponent: () =>
          import('@pages/performance/performance.component').then(
            (m) => m.PerformanceComponent,
          ),
      },
      {
        path: 'teams',
        loadComponent: () =>
          import('@pages/teams/teams.component').then((m) => m.TeamsComponent),
      },
      {
        path: 'connections',
        loadComponent: () =>
          import('@pages/connections/connections.component').then(
            (m) => m.ConnectionsComponent,
          ),
      },
      {
        path: 'plans',
        loadComponent: () =>
          import('@pages/plans/plans.component').then((m) => m.PlansComponent),
      },
      {
        path: 'admin',
        loadChildren: () =>
          import('@pages/admin/admin.routes').then((m) => m.ADMIN_ROUTES),
      },
      {
        // Theme Studio of @solercia/ui. The path is the one the "Apariencia"
        // menu entry of the backend catalog points to.
        path: 'settings/appearance',
        loadComponent: () =>
          import('@pages/theme-studio').then((m) => m.ThemeStudioPageComponent),
      },
      {
        path: 'task/:key',
        loadComponent: () =>
          import('@pages/task-detail/task-detail-page.component').then(
            (m) => m.TaskDetailPageComponent,
          ),
      },
    ],
  },
  {
    path: '**',
    loadComponent: () =>
      import('@pages/not-found/not-found-page.component').then(
        (m) => m.NotFoundPageComponent,
      ),
  },
];
