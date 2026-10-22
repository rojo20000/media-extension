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
| Helper problem: Native host has exited. Re-run install.ps1… (or "Error when communicating with the native messaging host") | The helper couldn't start, usually because Python was upgraded or moved, or the project folder moved. Run `install.ps1` again. If it still fails, look at `host\media_host.log`. |
| Helper problem: Couldn't create the media folder: … | The helper can't make `Music\media`. Check that your Music folder exists and that you can save files in it (OneDrive may be paused or signed out). |
| Helper problem: Couldn't open the log file: … | The project folder is read-only. Move it somewhere in your user folder, such as `Documents`, and run `install.ps1` again. Downloads still work in the meantime. |
| Helper problem: (anything else) | Look at `host\media_host.log`, which logs the most recent session. |

Other messages:

- **"Timed out reading this page (yt-dlp didn't answer in 60 s)"** means yt-dlp got stuck looking the page up, usually a network problem or a site change. Click **Try again**, and if it keeps happening, update yt-dlp.
- **"No watermark-free version offered"** on TikTok means TikTok didn't provide a clean copy of that video. The extension won't save the watermarked one under that button.
- **"Original file not offered without sign-in"** on SoundCloud means you'll get the best stream instead of the artist's original upload.
- **"Only a 30-second preview is available"** on SoundCloud means the track is Go+ or DRM-protected, so the button is disabled.
- **"(cover art not added)"** after a save means the file type (WAV, for example) can't hold artwork. The file itself is complete.
- **Age-restricted, members-only or private videos** need a signed-in account, which this extension doesn't use.
- **DRM-protected tracks** can't be downloaded. The popup shows yt-dlp's message.

If a file with the same name is already in the media folder, the new one is saved as `Title [id].ext`. Nothing is ever overwritten. Very long titles are shortened so the full path stays within Windows' 260-character limit.

If `install.ps1` says **Python's location has characters the helper's launcher can't use**, Python is in a folder whose name Windows can't write in a `.bat` file (and the drive has no short 8.3 names). Install Python in a folder with a plain-English name, then run `install.ps1` again.

To remove everything, run `uninstall.ps1`, then remove the extension in `chrome://extensions`.

## Manual test checklist

- [ ] YouTube music video, **Audio only**: an `.opus` or `.m4a` with cover art shows up in `Music\media`.
- [ ] YouTube 4K video, **Video**: the label says 2160p, and the saved `.mkv` plays at 2160p.
- [ ] SoundCloud track with downloads enabled: the label says **original file**.
- [ ] SoundCloud track without downloads: the label says **best stream**, with the note.
- [ ] **Check this first.** TikTok video, **Video, no watermark**: the saved video has no TikTok logo or username overlay. This couldn't be tested against the real TikTok during development, so if a watermark appears, stop using that button and report it.
- [ ] TikTok video, **Audio only**: the audio matches what plays in the video, voiceover included.
- [ ] TikTok photo post: only **Audio only** is offered, and it saves the post's sound.
- [ ] YouTube home page or a TikTok feed: the popup says "Open a specific video or track".
- [ ] A page with a plain `<video>`: it's listed and downloads.
- [ ] Download the same thing twice: the second file gets ` [id]` and the first is untouched.
- [ ] Close the popup mid-download and reopen it: the download's progress shows straight away (before the page finishes loading), continues, then shows **Saved**.
- [ ] Start a download, open another video in the same tab, and reopen the popup: the first download is still listed under its own label.
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
