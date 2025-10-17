import { Component } from '@angular/core';
import {FormBuilder, FormGroup, Validators} from '@angular/forms';
import {AuthService} from '../../core/auth';
import {Router} from '@angular/router';

@Component({
  selector: 'app-register',
  templateUrl: './register.component.html',
  styleUrl: './register.component.css'
})
export class RegisterComponent {

  form!: FormGroup;

  constructor(private fb: FormBuilder, private auth: AuthService, private router: Router) {
    this.form = this.fb.group({
      username: ['', Validators.required],
      firstName: ['', Validators.required],
      lastName: ['', Validators.required],
      birthDate: ['', Validators.required],
      email: ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required, Validators.minLength(6)]],
    });
  }
  loading = false; err?: string;


  submit() {
    if (this.form.invalid) return;
    this.loading = true;
    this.auth.register(this.form.value as any).subscribe({
      next: () => { this.loading = false; this.router.navigate(['/login']); },
      error: (e) => { this.err = 'Registracija nije uspela.'; this.loading = false; }
    });
  }
}
