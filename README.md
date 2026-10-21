# Media Downloader

A personal Chrome extension for Windows. Click its icon on a page to see the media there and save it at the best quality available. Files go to the **media** folder inside your Music folder.

- **YouTube:** the best video (up to 4K or 8K, picture and sound merged with no quality loss), or the audio only.
- **SoundCloud:** the artist's original file when they allow downloads, otherwise the best stream.
- **TikTok:** the video with no watermark, or its audio.
- **Other sites:** any video or audio files the page plays or links to. There's also a "Try this page with yt-dlp" button, which works on many other video sites.

Audio is saved in its original format (`.opus` or `.m4a`, for example), so nothing gets re-compressed. Tick **Convert audio to MP3** when a device needs MP3. Song files get the title, artist and cover art built in.

Downloads are done by [yt-dlp](https://github.com/yt-dlp/yt-dlp), running on your PC through a small helper. The extension never signs in or uses your cookies.

## Setup (one time)

1. **Get the files.** On GitHub, click **Code → Download ZIP** and extract it somewhere it can stay, such as `Documents\media-extension`. Or `git clone` the repository. Chrome and the helper use this folder from now on, so don't delete it.
2. **Load the extension.**
   1. Open `chrome://extensions`.
   2. Turn on **Developer mode** (top right).
   3. Click **Load unpacked** and choose the `extension` folder inside the project folder.

   Its ID should be `fcpcapkmpgmfjiohfmgemjolajbhonjb`.
3. **Install the helper.** Open PowerShell in the project folder (Shift + right-click the folder, then **Open PowerShell window here**) and run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File install.ps1
   ```

   It installs Python, yt-dlp, ffmpeg and Deno with `winget` if they're missing, registers the helper with Chrome, and prints the folder downloads will go to.
4. Pin the extension (puzzle-piece icon → pin) and open a YouTube video to try it.

Run `install.ps1` again whenever you move the project folder.

## Keeping it working

When a site changes and downloads start failing, the fix is almost always a newer yt-dlp:

```powershell
winget upgrade yt-dlp.yt-dlp
```

## Troubleshooting

The popup shows a yellow banner when something is wrong:

| Banner | What to do |
|---|---|
| Helper not installed | Run `install.ps1`, then reopen the popup. If you moved the folder, run it again. |
| yt-dlp not found / ffmpeg not found | Run `install.ps1` again. It records where these tools are. |
| Deno not found | Optional. Without it some YouTube formats may be missing. `winget install DenoLand.Deno`, then run `install.ps1` again. |
| Helper problem: … | Look at `host\media_host.log`, which logs the most recent session. |

Other messages:

- **"No watermark-free version offered"** on TikTok means TikTok didn't provide a clean copy of that video. The extension won't save the watermarked one under that button.
- **"Original file not offered without sign-in"** on SoundCloud means you'll get the best stream instead of the artist's original upload.
- **Age-restricted, members-only or private videos** need a signed-in account, which this extension doesn't use.
- **DRM-protected tracks** can't be downloaded. The popup shows yt-dlp's message.

If a file with the same name is already in the media folder, the new one is saved as `Title [id].ext`. Nothing is ever overwritten.

To remove everything, run `uninstall.ps1`, then remove the extension in `chrome://extensions`.

## Manual test checklist

- [ ] YouTube music video, **Audio only**: an `.opus` or `.m4a` with cover art shows up in `Music\media`.
- [ ] YouTube 4K video, **Video**: the label says 2160p, and the saved `.mkv` plays at 2160p.
- [ ] SoundCloud track with downloads enabled: the label says **original file**.
- [ ] SoundCloud track without downloads: the label says **best stream**, with the note.
- [ ] TikTok video, **Video, no watermark**: the saved video has no TikTok logo or username overlay.
- [ ] TikTok video, **Audio only**: the audio matches what plays in the video, voiceover included.
- [ ] TikTok photo post: only **Audio only** is offered.
- [ ] YouTube home page or a TikTok feed: the popup says "Open a specific video or track".
- [ ] A page with a plain `<video>`: it's listed and downloads.
- [ ] Download the same thing twice: the second file gets ` [id]` and the first is untouched.
- [ ] Close the popup mid-download and reopen it: progress continues, then shows **Saved**.
- [ ] Tick **Convert audio to MP3**: an `.mp3` is saved.

## Development

```
extension/   the Chrome extension (Manifest V3, no build step)
host/        the native messaging helper (Python, standard library only)
install.ps1  Windows setup; uninstall.ps1 undoes the registration
docs/        design and implementation plan
```

Tests run on any OS:

```sh
npm test                                                    # extension logic (Node 22+)
cd host && python3 -m unittest discover -s tests -t .       # helper
```
