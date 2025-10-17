import {CanActivate, CanActivateFn, Router} from '@angular/router';
import {Injectable} from '@angular/core';
import {AuthService} from '../core/auth';

@Injectable({ providedIn: 'root' })
export class AuthGuard implements CanActivate {
  constructor(private auth: AuthService, private router: Router) {}
  canActivate(): boolean {
    if (this.auth.isAuthenticated()) return true;
    this.router.navigate(['/login']);
    return false;
  }
}

