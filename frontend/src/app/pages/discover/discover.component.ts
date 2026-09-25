// src/app/pages/discover/discover.component.ts
import { Component } from '@angular/core';
import { FormBuilder, FormGroup } from '@angular/forms';
import {
  AlbumDetails,
  ArtistDetails,
  DiscoverItem,
  DiscoverService
} from '../../core/discover.service';
import {ContentService} from '../../core/content.service';

@Component({
  selector: 'app-discover',
  templateUrl: './discover.component.html',
  standalone: false
})
export class DiscoverComponent {
  form: FormGroup;

  items: DiscoverItem[] = [];
  nextKey: string | null = null;
  loading = false;
  error = '';

  // panel state
  showDetails = false;
  detailsType: 'ALBUM' | 'ARTIST' | null = null;
  albumDetails?: AlbumDetails;
  artistDetails?: ArtistDetails;
  detailsLoading = false;

  constructor(private fb: FormBuilder, private api: DiscoverService, private contentService: ContentService) {
    this.form = this.fb.group({
      genre: [''],
      type: [''],      // '' | 'album' | 'artist'
      limit: [12]
    });
  }

  search(reset = true): void {
    this.error = '';
    if (reset) {
      this.items = [];
      this.nextKey = null;
    }
    const genre = (this.form.value.genre ?? '').toString().trim().toLowerCase();
    const type  = this.form.value.type as ''|'album'|'artist';
    const limit = Number(this.form.value.limit) || 12;

    if (!genre) { this.error = 'Izaberi žanr'; return; }

    this.loading = true;
    this.api.discover(genre, type || undefined, limit, this.nextKey || undefined).subscribe({
      next: (res) => {
        if (reset) this.items = res.items ?? [];
        else this.items.push(...(res.items ?? []));
        this.nextKey = res.nextKey ?? null;
        this.loading = false;
      },
      error: () => {
        this.error = 'Greška pri učitavanju.';
        this.loading = false;
      }
    });
  }

  loadMore(): void {
    if (!this.nextKey || this.loading) return;
    this.search(false);
  }

  openDetails(it: DiscoverItem) {
    // Izvuci ID po tipu (bez any)
    if (it.entityType === 'ALBUM') {
      const id = it.albumId ?? it.id ?? it.PK?.split('#')[1];
      if (!id) return;

      this.showDetails = true;
      this.detailsLoading = true;
      this.detailsType = 'ALBUM';
      this.albumDetails = undefined;
      this.artistDetails = undefined;

      this.api.getAlbumDetails(id).subscribe({
        next: (res) => { this.albumDetails = res; this.detailsLoading = false; },
        error: (err) => { this.error = err?.error?.error || 'Greška pri učitavanju albuma'; this.detailsLoading = false; }
      });

    } else {
      const id = it.artistId ?? it.id ?? it.PK?.split('#')[1];
      if (!id) return;

      this.showDetails = true;
      this.detailsLoading = true;
      this.detailsType = 'ARTIST';
      this.albumDetails = undefined;
      this.artistDetails = undefined;

      this.api.getArtistDetails(id).subscribe({
        next: (res) => { this.artistDetails = res; this.detailsLoading = false; },
        error: (err) => { this.error = err?.error?.error || 'Greška pri učitavanju artista'; this.detailsLoading = false; }
      });
    }
  }

  closeDetails() {
    this.showDetails = false;
    this.detailsType = null;
    this.albumDetails = undefined;
    this.artistDetails = undefined;
  }

  item: any;
  subStatus?: string;

  private resolveTarget(input: any): { type: 'TRACK'|'ALBUM'|'ARTIST', id: string } | null {
    if (!input) return null;

    // TRACK
    const trackId =
      input.contentId ||
      (typeof input.id === 'string' && input.entityType === 'TRACK' ? input.id : null) ||
      (typeof input.PK === 'string' && input.PK.startsWith('CONTENT#') ? input.PK.split('#')[1] : null);
    if (trackId) return { type: 'TRACK', id: trackId };

    // ALBUM
    const albumId =
      input.albumId ||
      (typeof input.id === 'string' && (input.entityType === 'ALBUM' || this.detailsType === 'ALBUM') ? input.id : null) ||
      (typeof input.PK === 'string' && input.PK.startsWith('ALBUM#') ? input.PK.split('#')[1] : null);
    if (albumId) return { type: 'ALBUM', id: albumId };

    // ARTIST
    const artistId =
      input.artistId ||
      (typeof input.id === 'string' && (input.entityType === 'ARTIST' || this.detailsType === 'ARTIST') ? input.id : null) ||
      (typeof input.PK === 'string' && input.PK.startsWith('ARTIST#') ? input.PK.split('#')[1] : null);
    if (artistId) return { type: 'ARTIST', id: artistId };

    return null;
  }

  isSubscribing = false;

  subscribe(input?: any) {
    const candidate = input ?? this.item ?? this.albumDetails?.album ?? this.artistDetails?.artist;
    const target = this.resolveTarget(candidate);
    if (!target) { this.subStatus = '❌ Nije moguće odrediti tip ili ID.'; return; }

    this.isSubscribing = true;
    this.subStatus = '⏳ Pretplaćujem se...';

    this.contentService.subscribeToTarget(target.type, target.id).subscribe({
      next: () => {
        this.subStatus = '✅ Uspešno pretplaćen!';
        this.isSubscribing = false;
        setTimeout(() => { this.subStatus = undefined; }, 2500); // auto-hide
      },
      error: (err) => {
        this.subStatus = `❌ Greška: ${err?.error?.error || err?.message || err}`;
        this.isSubscribing = false;
        setTimeout(() => { this.subStatus = undefined; }, 4000);
      }
    });
  }



}
