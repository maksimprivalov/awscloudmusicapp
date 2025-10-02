import { Component, OnInit } from '@angular/core';
import { AuthService } from '../../../core/auth.service';
import { Router } from '@angular/router';

type Shortcut = { icon: string; title: string; desc: string; link: string };

@Component({
  selector: 'app-home-main',
  standalone: false,
  templateUrl: './home-main.component.html',
  styleUrls: ['./home-main.component.css'] // ⬅️ ispravljeno (plural)
})
export class HomeMainComponent implements OnInit {
  userRole: string | null = null;
  userRoles: string[] = [];

  constructor(private auth: AuthService, private router: Router) {}

  ngOnInit(): void {
    this.userRole = this.auth.getRole();
    const roles = this.auth.getRole();
    this.userRoles = Array.isArray(roles) ? roles : (roles ? [roles] : []);
  }

  onLogout() {
    this.auth.logout();
    this.router.navigate(['/login']);
  }

  shortcuts: Shortcut[] = [
    { icon: '🎤', title: 'Create artist', desc: 'Add new artist',            link: '/admin/artists/create' },
    { icon: '🎤', title: 'Artist',        desc: 'Edit and delete artist',    link: '/artist-table' },
    { icon: '🎶', title: 'Music',         desc: 'View all music',            link: '/tracks-table' },
    { icon: '📊', title: 'Albums',        desc: 'View all albums',           link: '/album-table' },
    { icon: '➕', title: 'Add music',     desc: 'Upload new track',          link: '/admin/upload' },
    { icon: '🌍', title: 'Discover',      desc: 'Explore content like users see it', link: '/discover' }
  ];

  goTo(link: string) {
    this.router.navigate([link]);
  }

  trackBy(_index: number, item: Shortcut): string {
    return item.link;
  }
}
