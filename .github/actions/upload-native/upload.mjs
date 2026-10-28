import {main} from '../../../tools/ci/artifact_upload.mjs';
import {nativeApplicationMaximumBytes} from '../../../tools/ci/artifact_policy.mjs';

await main({maximumBytes: nativeApplicationMaximumBytes});
