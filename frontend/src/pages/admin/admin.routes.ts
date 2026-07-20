import { Routes } from '@angular/router';

/**
 * Admin area routes, lazy-loaded under /admin (guarded by authGuard in the
 * parent route). Paths match the seeded menu paths so the menu-driven nav can
 * link straight to them: /admin/users, /admin/roles, /admin/menus,
 * /admin/dependencies.
 */
export const ADMIN_ROUTES: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'users' },
  {
    path: 'users',
    loadComponent: () =>
      import('./users/users-page.component').then(
        (m) => m.UsersPageComponent,
      ),
  },
  {
    path: 'roles',
    loadComponent: () =>
      import('./roles/roles-page.component').then(
        (m) => m.RolesPageComponent,
      ),
  },
  {
    path: 'organizations',
    loadComponent: () =>
      import('./organizations/organizations-page.component').then(
        (m) => m.OrganizationsPageComponent,
      ),
  },
  {
    path: 'menus',
    loadComponent: () =>
      import('./menus/menus-page.component').then(
        (m) => m.MenusPageComponent,
      ),
  },
  {
    path: 'dependencies',
    loadComponent: () =>
      import('./dependencies/dependencies-page.component').then(
        (m) => m.DependenciesPageComponent,
      ),
  },
];
