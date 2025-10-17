import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import {environment} from '../../../environments/environment';
import {ArtistCreateRequest, ArtistCreateResponse} from './artist.model';

@Injectable({ providedIn: 'root' })
export class ArtistService {
  private base = `${environment.apiBase}/artists`; // npr. POST /artists

  constructor(private http: HttpClient) {}

  create(payload: ArtistCreateRequest): Observable<ArtistCreateResponse> {
    return this.http.post<ArtistCreateResponse>(this.base, payload);
  }
}
