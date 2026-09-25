import {Component, OnInit} from '@angular/core';
import {ArtistDto, ArtistService, UpdateArtistPayload} from '../../core/artist.service';
import {HttpErrorResponse} from '@angular/common/http';
import {finalize} from 'rxjs/operators';

@Component({
  selector: 'app-artist-table',
  templateUrl: './artist-table.component.html',
  standalone: false
})
export class ArtistTableComponent implements OnInit {
  artists: ArtistDto[] = [];
  loading = false;
  error: string | null = null;
  deleting = new Set<string>();

  allGenres: string[] = ['pop','rock','lofi','rap','jazz','electronic','metal','folk'];

  // edit modal
  editing: ArtistDto | null = null;
  modalError: string | null = null;
  modalLoading = false;
  eName = '';
  eBio = '';
  eGenres: string[] = [];

  constructor(private svc: ArtistService) {}

  ngOnInit(): void { this.refresh(); }

  refresh(): void {
    this.loading = true; this.error = null;
    this.svc.getArtists().subscribe({
      next: list => { this.artists = (list || []).sort((a,b)=>a.name?.localeCompare(b.name||'')||0); this.loading=false; },
      error: (err: HttpErrorResponse) => {
        this.loading=false;
        this.error = err?.error?.error || err?.message || 'Failed to load artists';
      }
    });
  }

  openEdit(a: ArtistDto): void {
    this.editing = a;
    this.modalError = null;
    this.eName = a.name || '';
    this.eBio = a.bio || '';
    this.eGenres = Array.isArray(a.genres) ? [...a.genres] : [];
  }

  closeEdit(): void {
    this.editing = null;
    this.eName = this.eBio = '';
    this.eGenres = [];
  }

  saveEdit(): void {
    if (!this.editing) return;
    const payload: UpdateArtistPayload = {
      artistId: this.editing.artistId,
      name: this.eName,
      bio: this.eBio,
      genres: (this.eGenres || []).map(g => g.trim()).filter(Boolean)
    };
    this.modalLoading = true; this.modalError = null;
    this.svc.updateArtist(payload).pipe(finalize(()=>this.modalLoading=false))
      .subscribe({
        next: _ => { this.closeEdit(); this.refresh(); },
        error: (err: HttpErrorResponse) => {
          this.modalError = err?.error?.error || err?.message || 'Update failed';
        }
      });
  }

  onDelete(a: ArtistDto): void {
    if (!confirm(`Delete artist "${a.name}"?`)) return;
    this.deleting.add(a.artistId);
    this.svc.deleteArtist(a.artistId).subscribe({
      next: _ => { this.deleting.delete(a.artistId); this.refresh(); },
      error: (err: HttpErrorResponse) => {
        this.deleting.delete(a.artistId);
        this.error = err?.error?.error || err?.message || 'Delete failed';
      }
    });
  }

  trackById(_i: number, a: ArtistDto) { return a.artistId; }

}
