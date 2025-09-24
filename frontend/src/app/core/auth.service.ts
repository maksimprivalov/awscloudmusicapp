import { HttpClient } from '@angular/common/http';
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

          if (idTok) {
            localStorage.setItem(this.tokenKey, idTok);
          } else {

            localStorage.removeItem(this.tokenKey);
            throw new Error('Login response did not contain IdToken');
          }
        })
      );
  }

  isAuthenticated(): boolean {
    return !!localStorage.getItem(this.tokenKey);
  }

  getToken(): string | null {
    return localStorage.getItem(this.tokenKey);
  }

  logout() {
    localStorage.removeItem(this.tokenKey);
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
