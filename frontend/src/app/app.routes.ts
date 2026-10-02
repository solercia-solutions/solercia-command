import { Routes } from '@angular/router';
import { authGuard } from '@features/auth/auth.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'projects' },
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
    path: 'tasks/import',
    canActivate: [authGuard],
    loadComponent: () =>
      import('@pages/task-import/task-import-preview.component').then(
        (m) => m.TaskImportPreviewComponent,
      ),
  },
  {
    path: 'projects',
    canActivate: [authGuard],
    loadComponent: () =>
      import('@pages/projects/projects.component').then(
        (m) => m.ProjectsComponent,
      ),
  },
  {
    path: 'projects/:id',
    canActivate: [authGuard],
    loadComponent: () =>
      import(
        '@widgets/project-workspace/project-workspace.component'
      ).then((m) => m.ProjectWorkspaceComponent),
  },
  {
    path: 'hierarchy',
    canActivate: [authGuard],
    loadComponent: () =>
      import('@pages/hierarchy/hierarchy.component').then(
        (m) => m.HierarchyComponent,
      ),
  },
  {
    path: 'executive',
    canActivate: [authGuard],
    loadComponent: () =>
      import('@pages/executive/executive.component').then(
        (m) => m.ExecutiveComponent,
      ),
  },
  {
    path: 'performance',
    canActivate: [authGuard],
    loadComponent: () =>
      import('@pages/performance/performance.component').then(
        (m) => m.PerformanceComponent,
      ),
  },
  {
    path: 'teams',
    canActivate: [authGuard],
    loadComponent: () =>
      import('@pages/teams/teams.component').then((m) => m.TeamsComponent),
  },
  {
    path: 'connections',
    canActivate: [authGuard],
    loadComponent: () =>
      import('@pages/connections/connections.component').then(
        (m) => m.ConnectionsComponent,
      ),
  },
  {
    path: 'plans',
    canActivate: [authGuard],
    loadComponent: () =>
      import('@pages/plans/plans.component').then((m) => m.PlansComponent),
  },
  {
    path: 'admin',
    canActivate: [authGuard],
    loadChildren: () =>
      import('@pages/admin/admin.routes').then((m) => m.ADMIN_ROUTES),
  },
  {
    path: 'settings/appearance',
    canActivate: [authGuard],
    loadComponent: () =>
      import('@pages/settings/appearance/appearance-page.component').then(
        (m) => m.AppearancePageComponent,
      ),
  },
  {
    path: 'task/:key',
    canActivate: [authGuard],
    loadComponent: () =>
      import('@pages/task-detail/task-detail-page.component').then(
        (m) => m.TaskDetailPageComponent,
      ),
  },
  {
    path: '**',
    loadComponent: () =>
      import('@pages/not-found/not-found-page.component').then(
        (m) => m.NotFoundPageComponent,
      ),
  },
];
