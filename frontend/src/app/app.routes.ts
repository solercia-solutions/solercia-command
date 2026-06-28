import { Routes } from '@angular/router';
import { authGuard } from './core/auth.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'projects' },
  {
    path: 'login',
    loadComponent: () =>
      import('./features/auth/login.component').then((m) => m.LoginComponent),
  },
  {
    path: 'projects',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/projects/projects.component').then(
        (m) => m.ProjectsComponent,
      ),
  },
  {
    path: 'projects/:id',
    canActivate: [authGuard],
    loadComponent: () =>
      import(
        './features/projects/workspace/project-workspace.component'
      ).then((m) => m.ProjectWorkspaceComponent),
  },
  {
    path: 'executive',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/executive/executive.component').then(
        (m) => m.ExecutiveComponent,
      ),
  },
  {
    path: 'performance',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/performance/performance.component').then(
        (m) => m.PerformanceComponent,
      ),
  },
  {
    path: 'admin',
    canActivate: [authGuard],
    loadChildren: () =>
      import('./features/admin/admin.routes').then((m) => m.ADMIN_ROUTES),
  },
  {
    path: 'task/:key',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/task-detail/task-detail-page.component').then(
        (m) => m.TaskDetailPageComponent,
      ),
  },
  { path: '**', redirectTo: 'projects' },
];
