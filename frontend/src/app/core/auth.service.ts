import {HttpClient, HttpHeaders} from '@angular/common/http';
import { Injectable } from '@angular/core';
import { environment } from '../../environments/environment';
import { tap } from 'rxjs/operators';

export interface RegisterDto {
  first_name: string;
  last_name: string;
  birthdate: string; // YYYY-MM-DD
  email: string;
  password: string;
}
export interface LoginDto {
  email: string;
  password: string;
}

type LoginResLoose =
  | { idToken: string; accessToken?: string; refreshToken?: string }
  | { IdToken: string; AccessToken?: string; RefreshToken?: string }
  | { AuthenticationResult: { IdToken: string; AccessToken?: string; RefreshToken?: string } };

@Injectable({ providedIn: 'root' })
export class AuthService {
  private tokenKey = 'jwt';
  private accessKey  = 'accessToken';
  private refreshKey = 'refreshToken';
  private roleKey    = 'role';
  constructor(private http: HttpClient) {}

  register(payload: RegisterDto) {
    return this.http.post(`${environment.apiBase}/auth/register`, payload);
  }

  login(payload: LoginDto) {
    return this.http
      .post<LoginResLoose>(`${environment.apiBase}/auth/login`, payload)
      .pipe(
        tap((res) => {

          const idTok =
            (res as any)?.idToken ??
            (res as any)?.IdToken ??
            (res as any)?.AuthenticationResult?.IdToken;


          // access token
          const acc =
            (res as any)?.accessToken ??
            (res as any)?.AccessToken ??
            (res as any)?.AuthenticationResult?.AccessToken;


          // refresh token
          const ref =
            (res as any)?.refreshToken ??
            (res as any)?.RefreshToken ??
            (res as any)?.AuthenticationResult?.RefreshToken;

          if (!idTok) {
            this.logout();
            throw new Error('Login response did not contain IdToken');
          }

          localStorage.setItem(this.tokenKey, idTok);
          if (acc) localStorage.setItem(this.accessKey, acc);
          if (ref) localStorage.setItem(this.refreshKey, ref);

          const role = this.getRole();
          if (role) localStorage.setItem(this.roleKey, role);
        })
      );
  }

  isAuthenticated(): boolean {
    return !!localStorage.getItem(this.tokenKey);
  }

  getToken(): string | null {
    return localStorage.getItem(this.tokenKey);
  }

  getAccessToken(): string | null {
    return localStorage.getItem(this.accessKey);
  }
  getRefreshToken(): string | null {
    return localStorage.getItem(this.refreshKey);
  }

  logout() {
    localStorage.removeItem(this.tokenKey);
    localStorage.removeItem(this.accessKey);
    localStorage.removeItem(this.refreshKey);
    localStorage.removeItem(this.roleKey);
  }

  getClaims(): any | null {
    const tok = this.getToken();
    if (!tok) return null;
    try {
      const payload = tok.split('.')[1];

      const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
      return JSON.parse(json);
    } catch {
      return null;
    }
  }


  getRole(): string {
    const claims = this.getClaims();
    // Cognito grupe (preporučeno): ['Admin', 'User', ...]
    const cg = claims?.['cognito:groups'];
    const fromGroups = Array.isArray(cg) ? cg[0] : (typeof cg === 'string' ? cg : '');

    // alternativno custom claim 'custom:role' ili 'role'
    const custom = claims?.['custom:role'] ?? claims?.['role'] ?? '';

    const r = (fromGroups || custom || '').toString().toLowerCase();
    if (r.includes('admin')) return 'admin';
    if (r === 'ca' || r.includes(' ca')) return 'ca';
    if (r.includes('user')) return 'user';
    return r;
  }

  hasRole(expected: string | string[]): boolean {
    const role = this.getRole();
    const arr = Array.isArray(expected) ? expected : [expected];
    return arr.map(x => x.toLowerCase()).includes(role);
  }
  isCa(): boolean    { return this.hasRole('ca'); }
  isUser(): boolean  { return this.hasRole('user'); }
  isAdmin(): boolean {
    const claims = this.getClaims();
    if (!claims) return false;

    const groups = claims['cognito:groups'];
    if (!groups) return false;

    if (Array.isArray(groups)) {
      return groups.includes('Admin');
    }
    if (typeof groups === 'string') {
      return groups.split(',').includes('Admin') || groups.includes('Admin');
    }
    return false;
  }

}
