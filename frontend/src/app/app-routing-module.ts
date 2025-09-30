// app-routing-module.ts
import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { LoginComponent } from './pages/login/login.component';
import { RegisterComponent } from './pages/register/register.component';
import { DiscoverComponent } from './pages/discover/discover.component';
import {AuthGuard} from './guards/auth-guard';
import { ContentListComponent } from './pages/content-list/content-list.component';
import { ContentDetailComponent } from './pages/content-detail/content-detail.component';
import { AdminUploadComponent } from './pages/admin-upload/admin-upload.component';
import { AdminGuard } from './guards/admin-guard';
import {CreateArtistComponent} from './pages/create-artist/create-artist.component';
import {AlbumsTableComponent} from './pages/albums-table/albums-table.component';
import {ArtistTableComponent} from './pages/artist-table/artist-table.component';
import {TracksTableComponent} from './pages/tracks-table/tracks-table.component';

const routes: Routes = [
  { path: 'login', component: LoginComponent },
  { path: 'register', component: RegisterComponent },
  { path: 'discover', component: DiscoverComponent },
  { path: 'album-table', component: AlbumsTableComponent },
  { path: 'artist-table', component: ArtistTableComponent },
  { path: 'tracks-table', component: TracksTableComponent },
  { path: 'content', component: ContentListComponent },
  { path: 'content/:id', component: ContentDetailComponent },
  { path: 'admin/artists/create', component: CreateArtistComponent /*, canActivate: [AdminGuard]*/ },
  { path: 'admin/upload', component: AdminUploadComponent, canActivate: [AdminGuard] },
  { path: '', pathMatch: 'full', redirectTo: 'discover' },
  { path: '**', redirectTo: 'discover' },
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})
export class AppRoutingModule {}
