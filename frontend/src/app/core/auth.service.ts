import { Injectable } from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {environment} from '../../environments/environment';
import {tap} from 'rxjs';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private tokenKey = 'jwt';

  constructor(private http: HttpClient) {}

  register(payload: { firstName: string; lastName: string; birthDate: string; username: string; email: string; password: string; }) {
    return this.http.post(`${environment.apiBase}/auth/register`, payload);
  }

  login(payload: { username: string; password: string; }) {
    return this.http.post<{ idToken: string }>(`${environment.apiBase}/auth/login`, payload)
      .pipe(tap(res => localStorage.setItem(this.tokenKey, res.idToken)));
  }

  logout() { localStorage.removeItem(this.tokenKey); }

  isAuthenticated(): boolean { return !!localStorage.getItem(this.tokenKey); }

  getToken(): string | null { return localStorage.getItem(this.tokenKey); }
}

