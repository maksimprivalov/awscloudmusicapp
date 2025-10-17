import { Component } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import {AuthService, RegisterDto} from '../../core/auth.service';

@Component({
  selector: 'app-register',
  templateUrl: './register.component.html',
  standalone: false

})
export class RegisterComponent {
  form: FormGroup;
  loading = false;
  err?: string;

  constructor(private fb: FormBuilder, private auth: AuthService, private router: Router) {
    this.form = this.fb.group({
      firstName: ['', Validators.required],
      lastName: ['', Validators.required],
      birthDate: ['', Validators.required],
      username: ['', Validators.required],
      email: ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required, Validators.minLength(6)]],
    });
  }

  submit() {
    if (this.form.invalid) return;

    const payload: RegisterDto = {
      first_name: this.form.value.firstName!,
      last_name:  this.form.value.lastName!,
      birthdate:  this.form.value.birthDate!, // tip="date" daje YYYY-MM-DD
      email:      this.form.value.email!,
      password:   this.form.value.password!
    };

    this.loading = true;
    this.auth.register(payload).subscribe({
      next: () => { this.loading = false; this.router.navigate(['/login']); },
      error: (e) => {
        console.error('REGISTER ERROR', e);               
        this.err = e?.error?.error || e?.error || 'Registracija nije uspela.';
        this.loading = false;
      }    });
  }
}
