(function () {
    const toast = document.getElementById('toast');
    let toastTimer;

    function showToast(message) {
        if (!toast) return;
        toast.textContent = message;
        toast.classList.add('show');
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => toast.classList.remove('show'), 2400);
    }

    async function postJson(url, payload, keepalive) {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload || {}),
            keepalive: Boolean(keepalive)
        });
        if (!response.ok) throw new Error('Request failed');
        return response.json();
    }

    document.querySelectorAll('.save-button').forEach((button) => {
        button.addEventListener('click', async () => {
            const videoId = button.dataset.videoId;
            const saved = button.dataset.saved !== 'true';
            button.disabled = true;
            try {
                const data = await postJson(`/api/videos/${videoId}/save`, {
                    saved,
                    title: button.dataset.title,
                    thumbnail: button.dataset.thumbnail
                });
                button.dataset.saved = String(data.saved);
                button.classList.toggle('is-saved', data.saved);
                const icon = button.querySelector('span');
                if (icon) icon.textContent = data.saved ? '♥' : '♡';
                const label = button.querySelector('.save-label');
                if (label) label.textContent = data.saved ? 'Saved to your path' : 'Save to my path';
                showToast(data.saved ? 'Added to your learning path' : 'Removed from your path');
            } catch (error) {
                showToast('Could not save that lesson');
            } finally {
                button.disabled = false;
            }
        });
    });

    const playerElement = document.getElementById('player');
    if (!playerElement || !window.FOCUSTUBE_VIDEO_ID) return;

    let player;
    let progressTimer;
    const videoId = window.FOCUSTUBE_VIDEO_ID;
    const status = document.getElementById('player-status');
    const progressLabel = document.getElementById('player-progress');
    let noteTimestamp = null;

    function formatTime(seconds) {
        if (seconds === null || seconds === undefined) return 'Note';
        const minutes = Math.floor(seconds / 60);
        const remainder = String(Math.floor(seconds % 60)).padStart(2, '0');
        return `${minutes}:${remainder}`;
    }

    function appendNote(note) {
        const list = document.getElementById('notes-list');
        if (!list) return;
        const empty = list.querySelector('.notes-empty');
        if (empty) empty.remove();
        const article = document.createElement('article');
        article.className = 'note-item';
        article.dataset.noteId = note.id;
        const top = document.createElement('div');
        top.className = 'note-item-top';
        const time = document.createElement('span');
        time.textContent = formatTime(note.timestamp_seconds);
        const remove = document.createElement('button');
        remove.className = 'delete-note';
        remove.type = 'button';
        remove.dataset.noteId = note.id;
        remove.setAttribute('aria-label', 'Delete note');
        remove.textContent = '×';
        top.append(time, remove);
        const content = document.createElement('p');
        content.textContent = note.content;
        article.append(top, content);
        list.prepend(article);
    }

    const noteForm = document.getElementById('note-form');
    const noteContent = document.getElementById('note-content');
    const currentTimeButton = document.getElementById('add-current-time');
    if (currentTimeButton) {
        currentTimeButton.addEventListener('click', () => {
            if (!player || typeof player.getCurrentTime !== 'function') {
                showToast('Start the lesson to add a timestamp');
                return;
            }
            noteTimestamp = player.getCurrentTime() || 0;
            currentTimeButton.textContent = `At ${formatTime(noteTimestamp)}`;
            if (noteContent) noteContent.focus();
        });
    }
    if (noteForm) {
        noteForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            const content = noteContent ? noteContent.value.trim() : '';
            if (!content) return;
            try {
                const data = await postJson(`/api/videos/${videoId}/notes`, { content, timestamp_seconds: noteTimestamp });
                appendNote(data.note);
                noteContent.value = '';
                noteTimestamp = null;
                if (currentTimeButton) currentTimeButton.textContent = 'Add timestamp';
                showToast('Note saved');
            } catch (error) {
                showToast('Could not save note');
            }
        });
    }
    document.querySelectorAll('.delete-note').forEach((button) => {
        button.addEventListener('click', async () => {
            try {
                const response = await fetch(`/api/notes/${button.dataset.noteId}`, { method: 'DELETE' });
                if (!response.ok) throw new Error('Delete failed');
                button.closest('.note-item').remove();
                showToast('Note deleted');
            } catch (error) {
                showToast('Could not delete note');
            }
        });
    });

    function setStatus(message) {
        if (status) status.textContent = message;
    }

    async function saveProgress(completed, keepalive) {
        if (!player || typeof player.getCurrentTime !== 'function') return;
        const position = player.getCurrentTime() || 0;
        const duration = player.getDuration() || 0;
        try {
            const data = await postJson(`/api/videos/${videoId}/progress`, {
                position_seconds: position,
                duration_seconds: duration,
                completed: Boolean(completed)
            }, keepalive);
            if (progressLabel) progressLabel.textContent = `${data.progress_percent}% saved`;
        } catch (error) {
            // Progress is best effort; playback should continue if the network blinks.
        }
    }

    window.onYouTubeIframeAPIReady = function () {
        player = new YT.Player('player', {
            videoId,
            playerVars: { modestbranding: 1, rel: 0, playsinline: 1 },
            events: {
                onReady: () => setStatus('Ready when you are.'),
                onStateChange: (event) => {
                    if (event.data === YT.PlayerState.PLAYING) {
                        setStatus('Learning in progress');
                        clearInterval(progressTimer);
                        progressTimer = setInterval(() => saveProgress(false, false), 10000);
                    } else if (event.data === YT.PlayerState.PAUSED) {
                        setStatus('Paused · your place is saved');
                        clearInterval(progressTimer);
                        saveProgress(false, false);
                    } else if (event.data === YT.PlayerState.ENDED) {
                        setStatus('Lesson complete · nice work');
                        clearInterval(progressTimer);
                        saveProgress(true, false);
                    }
                }
            }
        });
    };

    window.addEventListener('pagehide', () => saveProgress(false, true));
})();
