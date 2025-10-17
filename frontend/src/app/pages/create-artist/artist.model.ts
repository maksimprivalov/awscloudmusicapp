export interface ArtistCreateRequest {
  name: string;
  bio: string;
  genres: string[];
}

export interface ArtistCreateResponse {
  message: string;
  artistId: string;
}
