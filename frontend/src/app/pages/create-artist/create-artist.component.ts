import { Component } from '@angular/core';
import {FormBuilder, FormGroup, Validators} from '@angular/forms';
import {ArtistService, ArtistCreateRequest} from '../../core/artist.service';


@Component({
  selector: 'app-create-artist',
  templateUrl: './create-artist.component.html',
  styleUrls: ['./create-artist.component.css'],
  standalone: false
})
export class CreateArtistComponent {
  form: FormGroup;
  submitting = false;
  error = '';
  success = '';

  genres: string[] = [];
  genreInput = '';

  constructor(private fb: FormBuilder, private artistSvc: ArtistService) {
    this.form = this.fb.group({
      name: ['', [Validators.required, Validators.minLength(2)]],
      bio: ['', [Validators.required, Validators.minLength(10)]],
    });
  }

  addGenre() {
    const g = (this.genreInput || '').trim();
    if (!g) return;
    const val = g.toLowerCase();
    if (!this.genres.includes(val)) this.genres.push(val);
    this.genreInput = '';
  }

  removeGenre(g: string) {
    this.genres = this.genres.filter(x => x !== g);
  }

  submit() {
    this.error = '';
    this.success = '';

    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.error = 'Proveri obavezna polja.';
      return;
    }
    if (this.genres.length === 0) {
      this.error = 'Dodaj bar jedan žanr.';
      return;
    }

    const payload: ArtistCreateRequest = {
      name: this.form.value.name.trim(),
      bio: this.form.value.bio.trim(),    // <<< "bio" – backend očekuje ovo ime!
      genres: this.genres,
    };

    this.submitting = true;
    this.artistSvc.create(payload).subscribe({
      next: (res) => {
        this.success = `Umetnik kreiran (ID: ${res.artistId}).`;
        this.submitting = false;
        this.form.reset();
        this.genres = [];
      },
      error: (err) => {
        // tipični slučajevi: 403 Admins only, 400 name/bio required
        const msg = err?.error?.error || err?.error?.message;
        this.error = msg || 'Došlo je do greške pri čuvanju.';
        this.submitting = false;
      }
    });
  }
}
