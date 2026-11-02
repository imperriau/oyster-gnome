// SPDX-License-Identifier: GPL-3.0-or-later
import Gio from 'gi://Gio';

/**
 * Artwork lookup. Each model has an asset directory named by its id as 4 lower-case hex digits
 * (e.g. assets/2420/); assets/generic/ is the fallback.
 *
 * - Static parts: <dir>/{case,left,right}.png, shown side by side.
 * - Optional 3D spin: <dir>/hero.json + the sprite sheet it names (see tools/pack_spin.py).
 *
 * All file access is asynchronous so nothing blocks the compositor's main loop.
 */

const PARTS = ['left', 'right', 'case'];

function modelDirs(extension, modelId) {
    const assets = extension.dir.get_child('assets');
    const hex = (modelId ?? 0).toString(16).padStart(4, '0').toLowerCase();
    return [assets.get_child(hex), assets.get_child('generic')];
}

function isNotFound(e) {
    return e.matches?.(Gio.IOErrorEnum, Gio.IOErrorEnum.NOT_FOUND);
}

/** @returns {Promise<boolean>} whether the file exists; other errors reject */
function exists(file, cancellable) {
    return new Promise((resolve, reject) => {
        file.query_info_async('standard::type', Gio.FileQueryInfoFlags.NONE,
            0, cancellable, (f, res) => {
                try {
                    f.query_info_finish(res);
                    resolve(true);
                } catch (e) {
                    if (isNotFound(e))
                        resolve(false);
                    else
                        reject(e);
                }
            });
    });
}

/** @returns {Promise<Uint8Array|null>} the file contents, or null if it does not exist */
function loadContents(file, cancellable) {
    return new Promise((resolve, reject) => {
        file.load_contents_async(cancellable, (f, res) => {
            try {
                const [, bytes] = f.load_contents_finish(res);
                resolve(bytes);
            } catch (e) {
                if (isNotFound(e))
                    resolve(null);
                else
                    reject(e);
            }
        });
    });
}

async function getPartIcon(dirs, part, cancellable) {
    for (const dir of dirs) {
        const f = dir.get_child(`${part}.png`);
        // eslint-disable-next-line no-await-in-loop -- in order: the first directory that has it wins
        if (await exists(f, cancellable))
            return new Gio.FileIcon({file: f});
    }
    return null;
}

/**
 * Only the model's own directory is searched: a generic spin would misrepresent other models.
 * A malformed hero.json is logged and treated as absent.
 */
async function getHero(dir, cancellable, logger) {
    const json = dir.get_child('hero.json');
    const bytes = await loadContents(json, cancellable);
    if (!bytes)
        return null;
    let meta;
    try {
        meta = JSON.parse(new TextDecoder().decode(bytes));
    } catch (e) {
        logger.warn(`bad ${json.get_path()}: ${e.message}`);
        return null;
    }
    if (!(meta.frames > 0 && meta.columns > 0 && meta.fps > 0) || typeof meta.sheet !== 'string') {
        logger.warn(`bad ${json.get_path()}: missing sheet, frames, columns or fps`);
        return null;
    }
    const file = dir.get_child(meta.sheet);
    if (!await exists(file, cancellable))
        return null;
    return {file, meta};
}

/**
 * Resolve every piece of artwork for a model.
 *
 * @returns {Promise<{icons: Object<string, Gio.Icon|null>, hero: {file: Gio.File, meta: object}|null}>}
 *   rejects with Gio.IOErrorEnum.CANCELLED if the cancellable fires
 */
export async function loadArtwork(extension, modelId, cancellable, logger) {
    const dirs = modelDirs(extension, modelId);
    const [hero, ...icons] = await Promise.all([
        getHero(dirs[0], cancellable, logger),
        ...PARTS.map(part => getPartIcon(dirs, part, cancellable)),
    ]);
    return {icons: Object.fromEntries(PARTS.map((part, i) => [part, icons[i]])), hero};
}
