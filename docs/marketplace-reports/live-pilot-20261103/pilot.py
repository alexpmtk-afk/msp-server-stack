"""Reviewed root-only E activation of unchanged accepted PR104; no installation ABC.

Self-contained build embeds nonsecret runner and expected service/runtime hashes.
Temporary activation is removed after the single bounded service run. Unknown
partial execution never retries HTTP; --hold only stops/cleans our exact controls.
"""
import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import pwd
import socket
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

ASSETS = {'code_sha': 'c1fee070e9efa0c925a78f266fdf03cb12a173cf', 'app_files': {'apps/msp_marketplace_reports/__init__.py': '62db73a52752cf06b4a4c5c9d04a4b44e78c3208361773dda8d27a6958bc7858', 'apps/msp_marketplace_reports/archive.py': 'a4d2800494da1464ed73ffa338d7fc501d1fce7ce3da5dceb45f0eb7f057a3a2', 'apps/msp_marketplace_reports/backfill_plan.py': 'b7811e304cebbe8ed3519df2fa82bd132b482690bb81272cce40f80e6ece4384', 'apps/msp_marketplace_reports/cli.py': 'bdeb1d586ffe01800c236b5687b2fcf060952cc394e213cb16083c8f0b0636e2', 'apps/msp_marketplace_reports/current_repair.py': '087fb13de1072f08aaaf49eb71cef7de42c9d804f099d582f963be013077cc44', 'apps/msp_marketplace_reports/existing_worker_bridge.py': '8cc5d3ce2454dc1f6c048b0f989f01143ff77dfac32abce0c863877d77f5c2be', 'apps/msp_marketplace_reports/generation_recovery.py': 'abd05ee172af8c8087af96898b88f430843ed93aab7b8849b242ed09514fe5de', 'apps/msp_marketplace_reports/generation_store.py': '1a981685a160031604e18d1aa3bd7728f2fb7b297183229d131fb24a34740fe2', 'apps/msp_marketplace_reports/ingest.py': 'f1d67ee3f0bde5e69012b45e8bcf72e1c4ccaeb1a6ed955ab3d7c740f1696c58', 'apps/msp_marketplace_reports/providers.py': 'ce761fcdc43a141663044156c460c9aa976f481cf1a7a2c778b0f3dcf0a57676', 'apps/msp_marketplace_reports/quota.py': 'ff3d0dd56605c8c6c9c98744b0e3ce75f15d99e2dda2a6ad68b366e4177ed422', 'apps/msp_marketplace_reports/runtime.py': 'a243543d53e5347dbcf42bf8e5b0558bf1e305bc9d708a0a06657d9dbd8f6ad5', 'apps/msp_marketplace_reports/shared_rate_limit.py': '1a9a165c30f03f7f50abc38564eb7134677a6e282248d3e56806fbc8ded33726', 'apps/msp_marketplace_reports/standalone_wb.py': 'a63d18fd8a4f781357385bde015fb1b06f830e28ece9b1b2b406177778b22266', 'apps/msp_marketplace_reports/versioned_archive.py': '7c49b1cf7c25cead17092d149030d4bc22652e26e66e7c890d96310122f3ad1f', 'apps/msp_marketplace_reports/wb_page_resume.py': 'a49c30c3725ea69a3dab28b1a5fe181112de1b6ce2740cd8478d7e546af180a8', 'apps/msp_marketplace_reports/wb_worker_adapter.py': 'd528b557ed8eec20f1ebab22dcab6fc1ba17feee4b8e2d9dd4506ac47a3cb59f'}, 'app_code_sha256': 'aac2431671d539d5653379b85b9a214d21e06fee7d1eb3f99361991949f465c5', 'runtime_files': {'lib/python3.12/site-packages/redis/__init__.py': 'cfd9db997a6d7928d0a77abe356259b763b34c17f817ea4c7767a1b6dd7d9a42', 'lib/python3.12/site-packages/redis/_defaults.py': 'b5df52a83c2e532f14cd24ab8bc29a358c303a34e506ba615c294f256be8144c', 'lib/python3.12/site-packages/redis/_himport_exec.py': '1f0847a1a6ba84a51b89d594eea7d4725f6b46c539ab18de2ed68d186b6e4461', 'lib/python3.12/site-packages/redis/background.py': '06cd9f38e669b16c07809e56ed718373578fbcc84f73a28ce588fe467fcdd183', 'lib/python3.12/site-packages/redis/backoff.py': 'b5033a2e1da0d858cc1fc89783de1baf6b14f5eae2e26116f456ceaccb746b3b', 'lib/python3.12/site-packages/redis/cache.py': 'c9f8d6343ef87ff3b8cce59c7a477eafd6f28cdc1193d3c037b79ea40f49fd81', 'lib/python3.12/site-packages/redis/client.py': 'dd4f59277910f1df863e73f6b95d584a7c6a8717e298c0649c914adb2cae77a6', 'lib/python3.12/site-packages/redis/cluster.py': '257ca2b72d1ca1c034b31eb2c7abb8e6c8175ec1bf3b635bf623aaae4863e206', 'lib/python3.12/site-packages/redis/connection.py': 'f036b858c369b423d05e161e46f12820455fe24dac9fc450d0831d96df91651b', 'lib/python3.12/site-packages/redis/crc.py': '67791716d918d8b76079f9d032e775c6be2f1b9518bc0f4b08ca8d317d72c2ee', 'lib/python3.12/site-packages/redis/credentials.py': '265e5fe3187d410bb7dffd78264616951c71c591da472c52bd9e4e5849b75a57', 'lib/python3.12/site-packages/redis/data_structure.py': 'a9366adecee0126655c3214135f2a790a9e6f6adfe1c7c6765f307f6c048c83e', 'lib/python3.12/site-packages/redis/driver_info.py': '6fdaeff030e12ba3b866528bb1b0dc22864deb2ccf21da0a6877f5d0d4782772', 'lib/python3.12/site-packages/redis/event.py': '6cb6a0eb6f325c70586f2aab6b2ce0ff5bcb6fa97c5e14307244d61daf78f746', 'lib/python3.12/site-packages/redis/exceptions.py': '4ad4d61f46ace0fde2e1f854025b881e6a12d708e70c29cb26f350e9e9b09b99', 'lib/python3.12/site-packages/redis/himport.py': 'd3bdce87282019bbc5a8ceef768518aacacec3995fca32064d13cb28f7f7057e', 'lib/python3.12/site-packages/redis/keyspace_notifications.py': '5cf82ba04032dea14b58632fcc5af4c97432231cb63712aea57c7897e5be6f40', 'lib/python3.12/site-packages/redis/lock.py': 'f8ddf9acd3cb3a67b303fc4e0fbd4988a5aff692c25cc364272fbd1a4f030bdc', 'lib/python3.12/site-packages/redis/maint_notifications.py': 'bc098a02ca5567fb1c1f4577c446b93285fbc05a331535e4aeb1f03a25f752d6', 'lib/python3.12/site-packages/redis/ocsp.py': 'e17d498065b5a702ae8d21185adc64049b4c59466d6a6a782a45fe67a9ec0702', 'lib/python3.12/site-packages/redis/py.typed': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'lib/python3.12/site-packages/redis/retry.py': '65546f2ba5f32b751019df770c74bccee29c435aca77b664cf0b821c4caf743d', 'lib/python3.12/site-packages/redis/sentinel.py': '0a74b66b5368ce64e6ec83bd8083446022b51823729e7ce0f457aae3090cc3bf', 'lib/python3.12/site-packages/redis/typing.py': '25e666a4708f30128bf987847635c3ebaad89ed65272711c1931a1154028c654', 'lib/python3.12/site-packages/redis/utils.py': '58cb6520cafaab7eaf914ce6cf524cfa0a8b5166105a5ad82b2ece07925fca28', 'lib/python3.12/site-packages/redis/_parsers/__init__.py': '8327f9769f75f0db8902458597cb17d59faa02f6d7ff8d3effb6024cce91be37', 'lib/python3.12/site-packages/redis/_parsers/base.py': '1f7f27043d0ccd788c2cfca8cd8f328d4dea7912c038348e31f185ef1740669d', 'lib/python3.12/site-packages/redis/_parsers/commands.py': '2e2faa801a83935e2c9228989f6253dca6b12dc9009723c0ff7bf8f714478891', 'lib/python3.12/site-packages/redis/_parsers/encoders.py': 'a079c70615d6358e0f1bdf06672742b645269616ffd6cbe9c9b08ca74526502a', 'lib/python3.12/site-packages/redis/_parsers/helpers.py': 'aefb0377ce681b76a10646013e0789a42bc45d4d8bb41d7189ad4cd03a054147', 'lib/python3.12/site-packages/redis/_parsers/hiredis.py': '79a50c15e8a782af06d3242f07d0e8bb0aa676a0c1b234a08df775bbd5da0fa1', 'lib/python3.12/site-packages/redis/_parsers/resp2.py': 'b617cb3bf6fb080dce3a03f36b1d2fd69f74acda50a685c5d54de019cc243889', 'lib/python3.12/site-packages/redis/_parsers/resp3.py': 'c8f4f0183016a40d0cb8c632369dbb27db6a610ce58b40a323337be609fcbdb5', 'lib/python3.12/site-packages/redis/_parsers/response_callbacks.py': 'b959b7f93d8df2de2302bd7b5f2c5422a851ddd9f4ce9771d7e9674a42ee42cf', 'lib/python3.12/site-packages/redis/_parsers/socket.py': '4af95236c3cebe7ce98badcf5d0f4ddf0efe59ac72d21b473fcf792b5f9bc323', 'lib/python3.12/site-packages/redis/asyncio/__init__.py': '6defc6455b5acc631443d3414c67da5d53b410e949c84e39e20165935d9e93e5', 'lib/python3.12/site-packages/redis/asyncio/_himport_exec.py': '58e9f5bf7aa5263c6aa1c5669fd8993796767f6e597bae85824946b0fbced454', 'lib/python3.12/site-packages/redis/asyncio/client.py': '1a525e44d30127cc7048c706505d8deb30e9c04aa7b3dda05e109eb9ce9d96c9', 'lib/python3.12/site-packages/redis/asyncio/cluster.py': 'a4030c09f33e2ff0ba67db44dd74b599e9e4e9b2a222dfa3fe0a5c58d0fe94ea', 'lib/python3.12/site-packages/redis/asyncio/connection.py': '245e337d16fa73d3a2a940c1aed15a610d5e6817a1ec49222a20798b7a12cb2d', 'lib/python3.12/site-packages/redis/asyncio/keyspace_notifications.py': '1d9c65b03243a5a56d4ec56913e1261be5e0411eeff47616c6ca8ef71240a02c', 'lib/python3.12/site-packages/redis/asyncio/lock.py': '589233fde2b49f8bb356d4b6b4c7a4a7d4931babe0e4cda3355cf525d6ff5a32', 'lib/python3.12/site-packages/redis/asyncio/maint_notifications.py': '8b6cfaae8aef7dd66b34463ebcb245b1b463ab40c6087b25a738aa05e654bf73', 'lib/python3.12/site-packages/redis/asyncio/retry.py': '55842c4ab8bcf1a31cdf115abdc3517b81464aae6041fffbd0b47e7a32c1fd85', 'lib/python3.12/site-packages/redis/asyncio/sentinel.py': '2d40215445353eaa1489b7ad2f129ffbf6e340bfc5f66470947a8ee198e7c7e9', 'lib/python3.12/site-packages/redis/asyncio/utils.py': '3244c8990f521402c585487055bbeedba07544063c29c81296956cc33d50948b', 'lib/python3.12/site-packages/redis/asyncio/http/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'lib/python3.12/site-packages/redis/asyncio/http/http_client.py': 'c1fb45f989782c0701364c72eb61ccdb1e4e4a6a5f133eaac4114cfb37edf6b5', 'lib/python3.12/site-packages/redis/asyncio/multidb/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'lib/python3.12/site-packages/redis/asyncio/multidb/client.py': '2b49db1bf329ba60d644e21b25735741baf52c231b1c672e61aa3c0640c6f23e', 'lib/python3.12/site-packages/redis/asyncio/multidb/command_executor.py': '206b5140a0505eb0c3a3fcc36f5455c17840341f431fd9ecf55b2ecc065f637b', 'lib/python3.12/site-packages/redis/asyncio/multidb/config.py': '6a0ffad6f785f8f9b60edf6a17e4d180d1f492d9487c3817a2256698c758b4d9', 'lib/python3.12/site-packages/redis/asyncio/multidb/database.py': '1d1b22e9716d6399d7a50729cded8a867ee4d9db27959d1bdd278ef807041da0', 'lib/python3.12/site-packages/redis/asyncio/multidb/event.py': 'efa192db637091e315c2d8ebd7750c7980f4a4007d2a83c3bca5948a7e03c07b', 'lib/python3.12/site-packages/redis/asyncio/multidb/failover.py': '4848651b6ac0e74333f9193e5b997fc0e4441e6290303cb149189202dd4d98c2', 'lib/python3.12/site-packages/redis/asyncio/multidb/failure_detector.py': 'd678a905f723b4b1fc5e9ad342f38113dcb49110bf62c3eccc43f32ca6e2494f', 'lib/python3.12/site-packages/redis/asyncio/multidb/healthcheck.py': '417eb461c23ee9b800be22f2517a2c59d308ef5f0a55fc69f5715a297c8331ba', 'lib/python3.12/site-packages/redis/asyncio/observability/__init__.py': 'cdc0cd568f4b9080d838bf1f2635f6e381b1cecab505b9e7b1a7686595bd1d1d', 'lib/python3.12/site-packages/redis/asyncio/observability/recorder.py': '4d9407e8b26475ec5a397b1aab1cc7c4138edc5d856c82a1a5e1c87649921fc5', 'lib/python3.12/site-packages/redis/auth/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'lib/python3.12/site-packages/redis/auth/err.py': '59891bb83233c29d52f9e02fb326ba40c94eea0f502176f33084ceb13597d319', 'lib/python3.12/site-packages/redis/auth/idp.py': '20c0c821bf6aef6bdb230b4537cbcf75a00a6554dd8741ee0b9ba3e6e7ea9b0e', 'lib/python3.12/site-packages/redis/auth/token.py': 'a98c00831156dd2f7740352aa75053b23ecf8fd6688678b119e397d2cec0b236', 'lib/python3.12/site-packages/redis/auth/token_manager.py': 'a6e2e4f58d04f948829ab871d128faddcf8113ef6177932f2f43b3b1bb24020c', 'lib/python3.12/site-packages/redis/commands/__init__.py': '713507f8c1af68b612d16ba8cadcaab4dd709e2c3603529b9145dca6f3926372', 'lib/python3.12/site-packages/redis/commands/cluster.py': '72fc6aa88a1694804765e343f05b600c0570c44decd3578fefa1d166e393f766', 'lib/python3.12/site-packages/redis/commands/core.py': '4a140d7df828003703553881ee91360d76b0c99152830461d4779d7bd9373076', 'lib/python3.12/site-packages/redis/commands/helpers.py': '9600714514725064929bd995ae7a563a8f5daccd842fe2fc55b5c5eada64663c', 'lib/python3.12/site-packages/redis/commands/policies.py': '47909f46f0678474e79c222f06c66c4e8435486b16c0caa3bb676caa9a832fb4', 'lib/python3.12/site-packages/redis/commands/redismodules.py': 'e4089a89b464725839656a4154b6bbdbcee42451be46678423d3e822ff90bb91', 'lib/python3.12/site-packages/redis/commands/sentinel.py': 'd25017b6083458edb209a29c8b7fb3efd94da329ca44d9ae2fb1a00644353193', 'lib/python3.12/site-packages/redis/commands/bf/__init__.py': 'db41900d3fff0be5548aff38788d8da8f18c27e5664e657297ed51dfda4fdc6c', 'lib/python3.12/site-packages/redis/commands/bf/commands.py': '25303b475db2792aaea9505da3e7bb25c41c01d0606ead516314ad0eb200aa6c', 'lib/python3.12/site-packages/redis/commands/bf/info.py': '4305906760a74542706efca37e02ea5335d569323b7b5f0f781144148566f0af', 'lib/python3.12/site-packages/redis/commands/json/__init__.py': 'e294b530cb865ebb69b7b6ba94954341c478a81c84be8863e661f4cd8efb49f5', 'lib/python3.12/site-packages/redis/commands/json/_util.py': '848050d532c24e05227dc2ec834c7c90995e731997840f48d333271e5424d07a', 'lib/python3.12/site-packages/redis/commands/json/commands.py': 'cf55c7eb05598cabbd59ea9c76434986779f253d40d7b30818bb9e9a7ac03bcc', 'lib/python3.12/site-packages/redis/commands/json/decoders.py': '6bf228315ff081e2725227c3e0fe874dc33db3a161ae27309b341c65199cf86c', 'lib/python3.12/site-packages/redis/commands/json/path.py': 'd3368eebfabf155324d4192191bed672bf001764dfafaf558642b2d480558690', 'lib/python3.12/site-packages/redis/commands/search/__init__.py': '5f95da449db78404f35c68b061b4c2c60e79b0a11f6aabd1fb0beb74cd3b67ff', 'lib/python3.12/site-packages/redis/commands/search/_util.py': 'f4ca7bd8e3b921be546df37bb976fe881ee14029b58d02d5f749acd8ff574865', 'lib/python3.12/site-packages/redis/commands/search/aggregation.py': '51f24f18bbc02ba4d0a4470b434c62522157a9e11857eee82f3d7f533f18837f', 'lib/python3.12/site-packages/redis/commands/search/commands.py': '821bdd88b3ba09724bba5e4785f9c1c692c03baa9214673ada28ddc5a9080783', 'lib/python3.12/site-packages/redis/commands/search/dialect.py': 'fbb33a924af7df1d0590cb4a994b1b791004eaac4b51ba9d242a88a3450a217a', 'lib/python3.12/site-packages/redis/commands/search/document.py': '83647e3d182afa3377dff18b5f36afbec7b872920704c7e33df3caeed9c4f467', 'lib/python3.12/site-packages/redis/commands/search/field.py': '29014a08655a0019fdbc362701c0748da3301b126a899f1f1091cffd589e051f', 'lib/python3.12/site-packages/redis/commands/search/hybrid_query.py': '72209c1643b365899b551f211a9ec10b5fcd4ecdc2cf6f456b38ba05e5b3992d', 'lib/python3.12/site-packages/redis/commands/search/hybrid_result.py': 'd55408c15c62e4b03df65f2bfa67db1227d1d3766cc1896f38f3e830cffa5226', 'lib/python3.12/site-packages/redis/commands/search/index_definition.py': '7f3df4c4adcf320736a7b0bf33b38125376255f64f9323506e71781bbe23f183', 'lib/python3.12/site-packages/redis/commands/search/profile_information.py': 'c3d49b3221db719d53a6c64c7bc70c2323b5846926e4686767f1aa8357de2ed7', 'lib/python3.12/site-packages/redis/commands/search/query.py': 'f7e082c636a47f9dc1a3028b4602dd0216486579566518d3ddb7d5cae764185c', 'lib/python3.12/site-packages/redis/commands/search/querystring.py': 'b0ad776573cc55e08c2212d1b06a3255d0c3ce8f9b138c5b80a26535a8846d34', 'lib/python3.12/site-packages/redis/commands/search/reducers.py': 'd8bc5777670cd45c6011b98476f241ec1b0329cca92ce535bbb145d9b9257955', 'lib/python3.12/site-packages/redis/commands/search/result.py': '5d02ac2a797d718f78bbf22033a6c723aa29da3ac35be6fd7c855befe567b924', 'lib/python3.12/site-packages/redis/commands/search/suggestion.py': '57fadeeacb830a835cd044e7fcfd6de7515e2b8a426a63f0c59471098f23b1c1', 'lib/python3.12/site-packages/redis/commands/timeseries/__init__.py': 'b0cd59aaab2c9932fbac189708dcdcf66f010071438103c477a49b05809f4c6a', 'lib/python3.12/site-packages/redis/commands/timeseries/commands.py': 'c7c40a96a730a8adb16a62e76a4610c76a5cbf51dd6ad63a5bf3f6ea608d15cc', 'lib/python3.12/site-packages/redis/commands/timeseries/info.py': '1432394b2d3c42b89b9c337adae8c298da271c6820f995786816a490bc5040b1', 'lib/python3.12/site-packages/redis/commands/timeseries/utils.py': '29797ca1ca54055ad33fb3bd7839aa2219e92d198afe796abf49dfec0e3c4e1d', 'lib/python3.12/site-packages/redis/commands/vectorset/__init__.py': '485ad09cd7678307fc64426026ce565f1cf2747201b84abf31628a833a8e0d1d', 'lib/python3.12/site-packages/redis/commands/vectorset/commands.py': 'f1773ff0d516f77538cac81fdd73c2721178a73fd0c09ee05dc895c0088f8ffa', 'lib/python3.12/site-packages/redis/commands/vectorset/utils.py': '900a72593cc6fc71204e3eb04b306e315cfea963213d282bf83a3fe5c1d24ba1', 'lib/python3.12/site-packages/redis/http/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'lib/python3.12/site-packages/redis/http/http_client.py': '46c7087723f631ec9cf22f1630ed9f00d5f75564fecad633c07310cc474d1284', 'lib/python3.12/site-packages/redis/multidb/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'lib/python3.12/site-packages/redis/multidb/circuit.py': '3375477d17c8cc8203aeb614462faacb877e2202b8e2606af04d376968535ed3', 'lib/python3.12/site-packages/redis/multidb/client.py': 'a679909af5e3cafb468204bd9226905c1a76abea9bbcb38bdf57955a421faa1e', 'lib/python3.12/site-packages/redis/multidb/command_executor.py': '092a3cbc6f043d17092b06bcc2572f649bca8d7e9f6e0a2a08cbf334fd7cc106', 'lib/python3.12/site-packages/redis/multidb/config.py': 'c242a9d462c843070479f144b896e8394b635b3f3059d416aa7b1284fc57414a', 'lib/python3.12/site-packages/redis/multidb/database.py': '677f60a607306f1abb78350802927a3994c647b349ebed004815b5a27dfa4200', 'lib/python3.12/site-packages/redis/multidb/event.py': 'f75fbc781197339bc3fd8a5083896a5474017f86673e71e3fb17599b17ede4b2', 'lib/python3.12/site-packages/redis/multidb/exception.py': '50397784de82f556c74ada1f04d9de20b9bd0091594a361513d3d918c693e8d9', 'lib/python3.12/site-packages/redis/multidb/failover.py': '8296dfa2346b5221c479dc9e2697ebb94dea4d2d353d44aaad5c7c00208376e5', 'lib/python3.12/site-packages/redis/multidb/failure_detector.py': '870b841c032028b4d18d01ca207b63ea2367b79df7bb3b7eeaa4627ae601de31', 'lib/python3.12/site-packages/redis/observability/__init__.py': 'cdf87713c5573031e4de9fb8f3b4e13b6b0d0825fb4e9b8613517f09dbfdf747', 'lib/python3.12/site-packages/redis/observability/attributes.py': '91cee5f4bc88c2319c96fae8889946c4fc79fe8792d68fa4ca4a46fd2ba25ea2', 'lib/python3.12/site-packages/redis/observability/config.py': '961d6435c36212484bd6c984a078c6c9a17876c8f6b03d646093b47d62fc5443', 'lib/python3.12/site-packages/redis/observability/metrics.py': '7da42c519c33d9ae0e0be36ae96fdf1cf2366b7204a90a46a60edd38a72a4a1f', 'lib/python3.12/site-packages/redis/observability/providers.py': 'e99375f9c466a9667bb9744055c0c802313181aea952d9c90fbec46d55ce9c8f', 'lib/python3.12/site-packages/redis/observability/recorder.py': '836758c84cf8299e3ad21ddb20acf700a0b011d582ff709fbb6f730a0a1f1cd3', 'lib/python3.12/site-packages/redis/observability/registry.py': '9c1145d9e6c3ae17e1768a98cda130aca29b676b683a49bf969ca2ac317b6686', 'lib/python3.12/site-packages/redis-8.1.0.dist-info/METADATA': '4668671cc6f1f9d6687255571a069e98f146dff48ba9840f38801b3e8cabba06', 'lib/python3.12/site-packages/redis-8.1.0.dist-info/WHEEL': '942926c567d0b1273d09f20295879abd37507845f6b683eab9f87d808df91100', 'lib/python3.12/site-packages/redis-8.1.0.dist-info/licenses/LICENSE': 'a57b250a5bf03d7afe55b74063313f2adb7b00d546c0ab149a89398333fe3cc8', 'lib/python3.12/site-packages/redis-8.1.0.dist-info/RECORD': '69bc1bf64c385d5cfe4ef085bda161ec648525c0b0e3f60d7f630eca02fb2a30', 'pyvenv.cfg': '100eb84011f5f5f6a050c283dadd77113c87194fb64e7a3b3cdd04aa0fa77059', 'bin/activate.fish': 'd8d92997dacb3e63f89c051e25f170cbe38ad9c0b71bd5388b2a0b3b75e29e74', 'bin/Activate.ps1': '3795a060dea7d621320d6d841deb37591fadf7f5592c5cb2286f9867af0e91df', 'bin/activate': '5787a1972b6b05e85cc90b047dd611e57211a61d129311bc3e696e4c8e2e15c2', 'bin/activate.csh': '76c9d75d239617f8d5fb1bd227394c86789701144dc2f64022535aab96ced3a1'}, 'runtime_links': {'lib64': 'lib', 'bin/python': 'python3', 'bin/python3': '/usr/bin/python3', 'bin/python3.12': 'python3'}, 'python_sha256': 'e50d468e8b0adfb05733f5b87b3cff34829c4a8c1aea50c865aa8bdfe4bb150f', 'base_unit_sha256': 'bb42eb914e7f0d47e303d99ea2c39d3e0fea5c31152ca1b1e4064659a3897cf4', 'plan_file_sha256': '38022de99e35af5971c90fe9a3d48e6570c2b542e6688e228a4cfc478114ecce', 'runner_sha256': 'ccaec90551d6414808d506661e6b7004e6814fd9d49225e0070762bd433529c2', 'runner_base64': 'IiIiT25lIGFwcHJvdmVkIFdCIHJlcG9ydCB0aHJvdWdoIHVuY2hhbmdlZCBQUjEwNCwgd2l0aCByZWRhY3RlZCBkaXNwYXRjaCBldmlkZW5jZS4iIiIKaW1wb3J0IGhhc2hsaWIKaW1wb3J0IGpzb24KaW1wb3J0IG9zCmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aAppbXBvcnQgc3RhdAppbXBvcnQgc3lzCmltcG9ydCB1cmxsaWIuZXJyb3IKClJFTEVBU0U9UGF0aCgnL29wdC9tY3AvcHJvamVjdHMvbXNwLW1hcmtldHBsYWNlLXJlcG9ydHMtcmVsZWFzZXMvYzFmZWUwNzBlOWVmYTBjOTI1YTc4ZjI2NmZkZjAzY2IxMmExNzNjZicpCkFSQ0hJVkU9UGF0aCgnL29wdC9tY3AvZGF0YS9tc3AtbWFya2V0cGxhY2UtcmVwb3J0cycpCkVYUEVDVEVEX1BBVEg9Jy9hcGkvZmluYW5jZS92MS9zYWxlcy1yZXBvcnRzL2RldGFpbGVkLzg4MzgwMTYzMicKVVJMPSdodHRwczovL2ZpbmFuY2UtYXBpLndpbGRiZXJyaWVzLnJ1JytFWFBFQ1RFRF9QQVRICgoKZGVmIGVtaXRfZXZlbnQocGF0aCxlbnRyeSk6CiAgICAiIiJObyBVUkwgcXVlcnkvaGVhZGVyL3Rva2VuL2JvZHkvcmVzcG9uc2UgY29udGVudCBpcyBldmVyIGpvdXJuYWxsZWQuIiIiCiAgICBmcm9tIGFwcHMubXNwX21hcmtldHBsYWNlX3JlcG9ydHMud2JfcGFnZV9yZXN1bWUgaW1wb3J0IF9jaGVja2VkCiAgICBfY2hlY2tlZChwYXRoKQogICAgZmQ9b3Mub3BlbihwYXRoLG9zLk9fV1JPTkxZfG9zLk9fQVBQRU5EfG9zLk9fQ1JFQVR8b3MuT19OT0ZPTExPVywwbzYwMCkKICAgIHRyeToKICAgICAgICBzdD1vcy5mc3RhdChmZCkKICAgICAgICBpZiBub3Qgc3RhdC5TX0lTUkVHKHN0LnN0X21vZGUpIG9yIHN0LnN0X3VpZCE9b3MuZ2V0ZXVpZCgpIG9yIHN0LnN0X25saW5rIT0xOnJhaXNlIFZhbHVlRXJyb3IoJ3Vuc2FmZSBldmVudCBqb3VybmFsJykKICAgICAgICB3aXRoIG9zLmZkb3BlbihmZCwnYScsY2xvc2VmZD1GYWxzZSkgYXMgZjoKICAgICAgICAgICAgZi53cml0ZShqc29uLmR1bXBzKGVudHJ5LHNvcnRfa2V5cz1UcnVlKSsnXG4nKTtmLmZsdXNoKCk7b3MuZmNobW9kKGZkLDBvNjAwKTtvcy5mc3luYyhmZCkKICAgIGZpbmFsbHk6b3MuY2xvc2UoZmQpCgoKZGVmIHZhbGlkYXRlX3Jlc3BvbnNlKHN0YXR1cyxyb3dzKToKICAgIGlmIHN0YXR1cz09MjA0OnJldHVybgogICAgaWYgc3RhdHVzIT0yMDA6cmV0dXJuICAjIGV4aXN0aW5nIFBSMTA0IGhhbmRsZXMgZXJyb3JzL2Nvb2xkb3duL1NUT1AuCiAgICBpZiB0eXBlKHJvd3MpIGlzIG5vdCBsaXN0IG9yIG5vdCByb3dzOnJhaXNlIFZhbHVlRXJyb3IoJ2ludmFsaWQgcGlsb3QgcmVzcG9uc2Ugc2hhcGUnKQogICAgZm9yIHIgaW4gcm93czoKICAgICAgICBpZiAodHlwZShyKSBpcyBub3QgZGljdCBvciB0eXBlKHIuZ2V0KCdyZXBvcnRJZCcpKSBpcyBub3QgaW50IG9yIHJbJ3JlcG9ydElkJ10hPTg4MzgwMTYzMgogICAgICAgICAgICBvciB0eXBlKHIuZ2V0KCdyZXBvcnRUeXBlJykpIGlzIG5vdCBpbnQgb3IgclsncmVwb3J0VHlwZSddIT0xCiAgICAgICAgICAgIG9yIHR5cGUoci5nZXQoJ3JyZElkJykpIGlzIG5vdCBpbnQgb3IgclsncnJkSWQnXTw9MCk6CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ3BpbG90IHJlc3BvbnNlIGlkZW50aXR5IG1pc21hdGNoJykKCgpjbGFzcyBBdWRpdGVkT3BlbmVyOgogICAgZGVmIF9faW5pdF9fKHNlbGYsaW5uZXIscGF0aCk6c2VsZi5pbm5lcj1pbm5lcjtzZWxmLnBhdGg9cGF0aAogICAgZGVmIG9wZW4oc2VsZixyZXF1ZXN0LHRpbWVvdXQpOgogICAgICAgIGlmIHJlcXVlc3QuZnVsbF91cmwhPVVSTCBvciByZXF1ZXN0LmdldF9tZXRob2QoKSE9J1BPU1QnOnJhaXNlIFZhbHVlRXJyb3IoJ2ZpeGVkIHBpbG90IGVuZHBvaW50IHJlcXVpcmVkJykKICAgICAgICBib2R5PWpzb24ubG9hZHMocmVxdWVzdC5kYXRhKQogICAgICAgIGlmIHNldChib2R5KSE9eydsaW1pdCcsJ3JyZElkJ30gb3IgdHlwZShib2R5WydsaW1pdCddKSBpcyBub3QgaW50IG9yIGJvZHlbJ2xpbWl0J10hPTEwMDAgb3IgdHlwZShib2R5WydycmRJZCddKSBpcyBub3QgaW50IG9yIGJvZHlbJ3JyZElkJ108MDpyYWlzZSBWYWx1ZUVycm9yKCdmaXhlZCBwaWxvdCByZXF1ZXN0IHJlcXVpcmVkJykKICAgICAgICBlbnRyeT17J2V2ZW50JzonSFRUUF9ESVNQQVRDSF9BVFRFTVBUJywncnJkSWQnOmJvZHlbJ3JyZElkJ119CiAgICAgICAgZW1pdF9ldmVudChzZWxmLnBhdGgsZW50cnkpICAjIGFmdGVyIGFjY2VwdGVkIHF1b3RhLCBCRUZPUkUgSFRUUC4KICAgICAgICB0cnk6CiAgICAgICAgICAgIHJlc3BvbnNlPXNlbGYuaW5uZXIub3BlbihyZXF1ZXN0LHRpbWVvdXQ9dGltZW91dCkKICAgICAgICBleGNlcHQgdXJsbGliLmVycm9yLkhUVFBFcnJvciBhcyBleGM6CiAgICAgICAgICAgIGVtaXRfZXZlbnQoc2VsZi5wYXRoLHsnZXZlbnQnOidIVFRQX1JFU1BPTlNFJywnc3RhdHVzJzppbnQoZXhjLmNvZGUpfSkKICAgICAgICAgICAgcmFpc2UKICAgICAgICBleGNlcHQgRXhjZXB0aW9uIGFzIGV4YzoKICAgICAgICAgICAgZW1pdF9ldmVudChzZWxmLnBhdGgseydldmVudCc6J0hUVFBfT1VUQ09NRV9VTktOT1dOJywnZXJyb3JfdHlwZSc6dHlwZShleGMpLl9fbmFtZV9ffSkKICAgICAgICAgICAgcmFpc2UKICAgICAgICBlbWl0X2V2ZW50KHNlbGYucGF0aCx7J2V2ZW50JzonSFRUUF9SRVNQT05TRScsJ3N0YXR1cyc6aW50KHJlc3BvbnNlLnN0YXR1cyl9KQogICAgICAgIHJldHVybiByZXNwb25zZQoKCmRlZiBtYWluKCosZXhwZWN0ZWRfdWlkPTk5NSk6CiAgICBpZiBvcy5nZXRldWlkKCkhPWV4cGVjdGVkX3VpZDpyYWlzZSBWYWx1ZUVycm9yKCdleGlzdGluZyBtc3AtcmVwb3J0cyByZXF1aXJlZCcpCiAgICBzeXMucGF0aC5pbnNlcnQoMCxzdHIoUkVMRUFTRSkpCiAgICBmcm9tIGFwcHMubXNwX21hcmtldHBsYWNlX3JlcG9ydHMgaW1wb3J0IHN0YW5kYWxvbmVfd2IgYXMgcwogICAgZnJvbSBhcHBzLm1zcF9tYXJrZXRwbGFjZV9yZXBvcnRzLnJ1bnRpbWUgaW1wb3J0IFJlYWRPbmx5SFRUUAogICAgZnJvbSBhcHBzLm1zcF9tYXJrZXRwbGFjZV9yZXBvcnRzLndiX3BhZ2VfcmVzdW1lIGltcG9ydCBfZGlyLF9yZWFkX2pzb24sX3ZhbGlkYXRlX3N0YXRlLF92ZXJpZnlfcGFnZXMKICAgIHBsYW49cy5yZWFkX2NvbnRyb2woUkVMRUFTRS8ncGlsb3QtcGxhbi5qc29uJykKICAgIGlmIHBsYW4hPXsnc2NoZW1hJzoxLCdjYWJpbmV0Jzond2JfbGFzZXJfbWFzdGVyJywneWVhcic6MjAyNiwncmVwb3J0X2lkJzo4ODM4MDE2MzIsJ3JlcG9ydF90eXBlJzoxLCdtYXhfc2VuZF9lbnRyaWVzJzozfTpyYWlzZSBWYWx1ZUVycm9yKCdwaWxvdCBwbGFuIGRyaWZ0JykKICAgIGF1dGg9cy5yZWFkX2F1dGhvcml6YXRpb24oJy9ldGMvbXNwLW1hcmtldHBsYWNlLXJlcG9ydHMtZXhlY3V0b3IvYXBwcm92YWwuanNvbicpCiAgICBldmVudHM9QVJDSElWRS8nLndiLWV4ZWN1dG9yJy8nRS04ODM4MDE2MzItZXZlbnRzLmpzb25sJwogICAgY2xhc3MgU2VuZGVyKFJlYWRPbmx5SFRUUCk6CiAgICAgICAgZGVmIF9fY2FsbF9fKHNlbGYscmVxdWVzdCk6CiAgICAgICAgICAgIGlmIHJlcXVlc3QucGF0aCE9RVhQRUNURURfUEFUSCBvciByZXF1ZXN0Lm1hcmtldHBsYWNlIT0nd2InOnJhaXNlIFZhbHVlRXJyb3IoJ3BpbG90IHJlcG9ydCBzY29wZScpCiAgICAgICAgICAgIHJlc3VsdD1zdXBlcigpLl9fY2FsbF9fKHJlcXVlc3QpCiAgICAgICAgICAgIHZhbGlkYXRlX3Jlc3BvbnNlKCpyZXN1bHQpCiAgICAgICAgICAgIHJldHVybiByZXN1bHQKICAgIGRlZiBmYWN0b3J5KCk6CiAgICAgICAgY3JlZD1QYXRoKG9zLmVudmlyb25bJ0NSRURFTlRJQUxTX0RJUkVDVE9SWSddKS8nY2FiaW5ldHMuanNvbicKICAgICAgICBzZW5kZXI9U2VuZGVyKGNhYmluZXQ9J3diX2xhc2VyX21hc3RlcicsY3JlZGVudGlhbHNfZmlsZT1jcmVkLHN0YXRlX3Jvb3Q9QVJDSElWRSkKICAgICAgICBzZW5kZXIub3BlbmVyPUF1ZGl0ZWRPcGVuZXIoc2VuZGVyLm9wZW5lcixldmVudHMpCiAgICAgICAgcmV0dXJuIHNlbmRlcgogICAgb3V0Y29tZT1zLnJ1bl9ib3VuZGVkKEFSQ0hJVkUscGxhbixhdXRoLGZhY3RvcnkpCiAgICBmb2xkZXI9X2RpcihBUkNISVZFLCd3Yl9sYXNlcl9tYXN0ZXInLDIwMjYsODgzODAxNjMyLDEpCiAgICBwYWdlX3N0YXRlPV9yZWFkX2pzb24oZm9sZGVyLydzdGF0ZS5qc29uJykKICAgIHN1bW1hcnk9eydleGVjdXRvcic6b3V0Y29tZSwncmVwb3J0X2lkJzo4ODM4MDE2MzIsJ3JlcG9ydF90eXBlJzoxLCdjYWJpbmV0Jzond2JfbGFzZXJfbWFzdGVyJ30KICAgIGlmIHBhZ2Vfc3RhdGU6CiAgICAgICAgX3ZhbGlkYXRlX3N0YXRlKHBhZ2Vfc3RhdGUsJ3diX2xhc2VyX21hc3RlcicsMjAyNiw4ODM4MDE2MzIsMSk7X3ZlcmlmeV9wYWdlcyhmb2xkZXIscGFnZV9zdGF0ZSw4ODM4MDE2MzIsMSkKICAgICAgICBzdW1tYXJ5LnVwZGF0ZShwYWdlcz1sZW4ocGFnZV9zdGF0ZVsncGFnZXMnXSksY3Vyc29yPXBhZ2Vfc3RhdGVbJ2N1cnJlbnRfcnJkX2lkJ10sCiAgICAgICAgICAgICAgICAgICAgICAgcGFnZV9oYXNoZXM9W3BbJ3NoYTI1NiddIGZvciBwIGluIHBhZ2Vfc3RhdGVbJ3BhZ2VzJ11dLAogICAgICAgICAgICAgICAgICAgICAgIHRlcm1pbmFsPXBhZ2Vfc3RhdGVbJ3N0YXR1cyddPT0nU1RBR0VEX0NPTVBMRVRFJyxzdGFnZV9wYXRoPXN0cihmb2xkZXIpLAogICAgICAgICAgICAgICAgICAgICAgIHJvd3Nfc3RhZ2VkPXN1bShsZW4oX3JlYWRfanNvbihmb2xkZXIvKCdwYWdlLScrc3RyKHBbJ2N1cnNvciddKSsnLmpzb24nKSxyZXF1aXJlZD1UcnVlKVsncm93cyddKSBmb3IgcCBpbiBwYWdlX3N0YXRlWydwYWdlcyddKSkKICAgICAgICBpZiBwYWdlX3N0YXRlWydzdGF0dXMnXT09J1NUQUdFRF9DT01QTEVURSc6CiAgICAgICAgICAgIGZyb20gYXBwcy5tc3BfbWFya2V0cGxhY2VfcmVwb3J0cy53Yl93b3JrZXJfYWRhcHRlciBpbXBvcnQgX3JlYWRfY292ZXJhZ2UsX3ZhbGlkYXRlX2NvdmVyYWdlCiAgICAgICAgICAgIGNvdmVyYWdlPV9yZWFkX2NvdmVyYWdlKGZvbGRlcik7X3ZhbGlkYXRlX2NvdmVyYWdlKEFSQ0hJVkUsJ3diX2xhc2VyX21hc3RlcicsMjAyNiw4ODM4MDE2MzIsMSxjb3ZlcmFnZSkKICAgICAgICAgICAgc3VtbWFyeS51cGRhdGUocm93cz1jb3ZlcmFnZVsncm93cyddLGdlbmVyYXRpb249Y292ZXJhZ2VbJ2dlbmVyYXRpb24nXSxtYW5pZmVzdF9zaGEyNTY9Y292ZXJhZ2VbJ21hbmlmZXN0X3NoYTI1NiddLAogICAgICAgICAgICAgICAgICAgICAgICAgICByZXBvcnRfZGV0YWlsX2NvbXBsZXRlPVRydWUsZmluYW5jaWFsX3JlY29uY2lsaWF0aW9uX3Byb3Zlbj1GYWxzZSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgYXJjaGl2ZV9zY29wZT1zdHIoQVJDSElWRS8nLmI3LWdlbmVyYXRpb25zL3diX3dlZWtseV9maW5hbmNlX21haW4vd2JfbGFzZXJfbWFzdGVyLzIwMjYnKSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgcHVibGlzaGVkX2dlbmVyYXRpb25fcGF0aD1zdHIoQVJDSElWRS8nLmI3LWdlbmVyYXRpb25zL3diX3dlZWtseV9maW5hbmNlX21haW4vd2JfbGFzZXJfbWFzdGVyLzIwMjYvZ2VuZXJhdGlvbnMnL2NvdmVyYWdlWydnZW5lcmF0aW9uJ10pKQogICAgICAgIGVsc2U6c3VtbWFyeVsncmVwb3J0X2RldGFpbF9jb21wbGV0ZSddPUZhbHNlCiAgICBpZiBldmVudHMuZXhpc3RzKCk6CiAgICAgICAgZnJvbSBhcHBzLm1zcF9tYXJrZXRwbGFjZV9yZXBvcnRzLndiX3BhZ2VfcmVzdW1lIGltcG9ydCBfY2hlY2tlZAogICAgICAgIF9jaGVja2VkKGV2ZW50cykKICAgICAgICBpZiBldmVudHMuc3RhdCgpLnN0X3NpemU+MTYzODQ6cmFpc2UgVmFsdWVFcnJvcignZXZlbnRzIG92ZXJzaXplZCcpCiAgICAgICAgdmFsdWVzPVtqc29uLmxvYWRzKGxpbmUpIGZvciBsaW5lIGluIGV2ZW50cy5yZWFkX3RleHQoKS5zcGxpdGxpbmVzKCldCiAgICAgICAgc3VtbWFyeS51cGRhdGUoaHR0cF9kaXNwYXRjaF9hdHRlbXB0c190aGlzX3J1bj1zdW0odi5nZXQoJ2V2ZW50Jyk9PSdIVFRQX0RJU1BBVENIX0FUVEVNUFQnIGZvciB2IGluIHZhbHVlcyksCiAgICAgICAgICAgICAgICAgICAgICAgaHR0cF9yZXNwb25zZV9zdGF0dXNlcz1bdlsnc3RhdHVzJ10gZm9yIHYgaW4gdmFsdWVzIGlmIHYuZ2V0KCdldmVudCcpPT0nSFRUUF9SRVNQT05TRSddLAogICAgICAgICAgICAgICAgICAgICAgIGh0dHBfb3V0Y29tZXNfdW5rbm93bj1zdW0odi5nZXQoJ2V2ZW50Jyk9PSdIVFRQX09VVENPTUVfVU5LTk9XTicgZm9yIHYgaW4gdmFsdWVzKSkKICAgIGVsc2U6CiAgICAgICAgc3VtbWFyeS51cGRhdGUoaHR0cF9kaXNwYXRjaF9hdHRlbXB0c190aGlzX3J1bj0wLGh0dHBfcmVzcG9uc2Vfc3RhdHVzZXM9W10saHR0cF9vdXRjb21lc191bmtub3duPTApCiAgICBwcmludChqc29uLmR1bXBzKHN1bW1hcnksc29ydF9rZXlzPVRydWUpKQogICAgcmV0dXJuIDAgaWYgb3V0Y29tZVsnc3RhdHVzJ109PSdET05FJyBlbHNlIDIKCmlmIF9fbmFtZV9fPT0nX19tYWluX18nOgogICAgdHJ5OnJhaXNlIFN5c3RlbUV4aXQobWFpbigpKQogICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBleGM6CiAgICAgICAgcHJpbnQoanNvbi5kdW1wcyh7J3dyYXBwZXJfc3RhdHVzJzonU1RPUF9PUl9VTkNFUlRBSU4nLCdlcnJvcl90eXBlJzp0eXBlKGV4YykuX19uYW1lX199KSk7cmFpc2UgU3lzdGVtRXhpdCgxKQo=', 'synthetic_probe_sha256': '80c1ef163ec5e31c9850232ff180e09decb85cd1e2dbd3c8867962c1e785d187'}
CODE='c1fee070e9efa0c925a78f266fdf03cb12a173cf'
RELEASE=Path('/opt/mcp/projects/msp-marketplace-reports-releases')/CODE
ARCHIVE=Path('/opt/mcp/data/msp-marketplace-reports')
UNIT=Path('/etc/systemd/system/msp-wb-pilot.service')
SERVICE='msp-wb-pilot.service'
CONTROL=Path('/etc/msp-marketplace-reports-executor')
APPROVAL=CONTROL/'approval.json'
REDIS_ENV=CONTROL/'redis-runtime.env'
PILOT=Path('/etc/msp-marketplace-reports-pilot/wb_laser_master.json')
MASTER=Path('/etc/msp-marketplace-reports/cabinets.json')
SYNTHETIC=Path('/var/lib/msp-quota-probe-i8kqe69o/result.json')
STATE=Path('/var/lib/msp-wb-E-883801632')
DROP_DIR=Path('/run/systemd/system/msp-wb-pilot.service.d')
DROP=DROP_DIR/'90-msp-E-883801632.conf'
PUBLIC=Path('/opt/mcp/report-run-results')
PLAN={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':883801632,'report_type':1,'max_send_entries':3}


def sha(data):return hashlib.sha256(data).hexdigest()
def encoded(doc):return (json.dumps(doc,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode()

def trusted(p,uid=0,mode=None):
    st=p.lstat()
    if stat.S_ISLNK(st.st_mode) or st.st_uid!=uid or st.st_mode&0o022:raise ValueError('untrusted path')
    if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):raise ValueError('inode type')
    if stat.S_ISREG(st.st_mode) and st.st_nlink!=1:raise ValueError('hardlink')
    if mode is not None and stat.S_IMODE(st.st_mode)!=mode:raise ValueError('mode drift')
    return st

def parents(p):
    for item in [p,*p.parents]:trusted(item)

def syncdir(p):
    fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)

def write_new(p,data,mode=0o600):
    fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,mode)
    try:
        with os.fdopen(fd,'wb',closefd=False) as f:
            f.write(data);f.flush();os.fchown(fd,0,0);os.fchmod(fd,mode);os.fsync(fd)
    finally:os.close(fd)
    syncdir(p.parent)

def strict_json(raw):
    def pairs(items):
        d={}
        for k,v in items:
            if k in d:raise ValueError('duplicate JSON key')
            d[k]=v
        return d
    return json.loads(raw,object_pairs_hook=pairs)

def run(args,timeout=45):
    p=subprocess.run(args,capture_output=True,timeout=timeout,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8'})
    if p.returncode:raise RuntimeError('command failed: '+Path(args[0]).name)
    return p.stdout

def show():
    raw=run(['/usr/bin/systemctl','show',SERVICE,'--property=ActiveState,SubState,DropInPaths,User,Group,PrivateNetwork,IPAddressAllow,IPAddressDeny,EnvironmentFiles,Restart']).decode()
    return dict(line.split('=',1) for line in raw.splitlines() if '=' in line)

def redis_config(raw):
    values={}
    for line in raw.decode().splitlines():
        k,sep,v=line.partition('=')
        if not sep or k not in ('MARKETPLACE_MCP_REDIS_URL','MARKETPLACE_REQUIRE_REDIS') or k in values or any(c in v for c in '\\"\'\r\x00'):
            raise ValueError('Redis EnvFile format')
        values[k]=v
    if set(values)!= {'MARKETPLACE_MCP_REDIS_URL','MARKETPLACE_REQUIRE_REDIS'} or values['MARKETPLACE_REQUIRE_REDIS']!='1':raise ValueError('Redis required')
    u=urlsplit(values['MARKETPLACE_MCP_REDIS_URL'])
    if (u.scheme!='redis' or u.hostname!='127.0.0.1' or u.port!=16379 or u.path!='/0' or u.username!='quota_runtime' or not u.password or u.query or u.fragment):raise ValueError('approved Redis target required')

def verify_credentials(pilot,master,now):
    one=strict_json(pilot);all_=strict_json(master)
    if type(one) is not dict or type(all_) is not dict or set(one)!= {'wb_laser_master'} or type(one['wb_laser_master']) is not dict or type(all_.get('wb_laser_master')) is not dict or one['wb_laser_master'].get('token')!=all_['wb_laser_master'].get('token'):raise ValueError('pilot/master alias mismatch')
    token=one['wb_laser_master'].get('token')
    if type(token) is not str or len(token.split('.'))!=3:raise ValueError('WB credential structure')
    piece=token.split('.')[1];claims=strict_json(base64.urlsafe_b64decode(piece+'='*(-len(piece)%4)))
    if not isinstance(claims.get('sid'),(str,int)) or isinstance(claims.get('sid'),bool) or not str(claims['sid']):raise ValueError('seller identity unavailable')
    if type(claims.get('exp')) is not int or claims['exp']<=now:raise ValueError('WB credential expired/expiry unknown')
    return {'pilot_master_match':True,'seller_identity_present':True,'expiry_local_check':'PASS',
            'signature_or_finance_permission_proven':False}

def resolve_allowlist():
    addresses=sorted({str(ipaddress.ip_address(x[4][0])) for x in socket.getaddrinfo('finance-api.wildberries.ru',443,type=socket.SOCK_STREAM)})
    if not addresses or len(addresses)>32 or any(not ipaddress.ip_address(x).is_global for x in addresses):raise ValueError('finance DNS not public/bounded')
    dns=[]
    for line in Path('/etc/resolv.conf').read_text().splitlines():
        fields=line.split()
        if len(fields)>=2 and fields[0]=='nameserver':dns.append(str(ipaddress.ip_address(fields[1])))
    if not dns or len(dns)>6:raise ValueError('DNS resolver inventory')
    ips=sorted(set(addresses+dns+['127.0.0.1']))
    return [x+('/32' if ipaddress.ip_address(x).version==4 else '/128') for x in ips]

def dropin_text(program,allow):
    if any(c in str(program) for c in '\n\r %'):raise ValueError('program path')
    # Only this service gets ephemeral egress; application additionally fixes HTTPS host/path.
    return ('[Service]\nPrivateNetwork=no\nEnvironmentFile='+str(REDIS_ENV)+'\n'
        'Environment=MARKETPLACE_REQUIRE_REDIS=1 MSP_REPORTS_SHARED_QUEUE_VERIFIED=YES\n'
        'Environment=HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= http_proxy= https_proxy= all_proxy=\n'
        'IPAddressDeny=any\nIPAddressAllow='+ ' '.join(allow)+'\n'
        'ExecStart=\nExecStart='+str(RELEASE/'.venv/bin/python')+' -I -B '+str(program)+'\n'
        'StandardOutput=file:'+str(STATE/'worker-output.json')+'\n'
        'StandardError=file:'+str(STATE/'worker-stderr.txt')+'\n').encode()

def safe_remove(p,expected):
    if not p.exists() and not p.is_symlink():return
    trusted(p)
    if sha(p.read_bytes())!=expected:raise ValueError('changed control; no removal')
    p.unlink();syncdir(p.parent)

def cleanup(ownership,stop=False):
    # Never stop other services, never delete page/budget/data/credentials.
    if stop and show()['ActiveState'] not in ('inactive','failed'):
        for p,key in [(APPROVAL,'approval_sha256'),(DROP,'dropin_sha256')]:
            trusted(p)
            if sha(p.read_bytes())!=ownership.get(key):raise ValueError('foreign active pilot; no stop')
        run(['/usr/bin/systemctl','stop',SERVICE],timeout=90)
    if show()['ActiveState'] not in ('inactive','failed'):raise ValueError('pilot still active')
    for p,key in [(APPROVAL,'approval_sha256'),(DROP,'dropin_sha256')]:
        if key in ownership:safe_remove(p,ownership[key])
    if DROP_DIR.exists():
        trusted(DROP_DIR)
        if list(DROP_DIR.iterdir()):raise ValueError('unexpected runtime dropin')
        DROP_DIR.rmdir();syncdir(DROP_DIR.parent)
    run(['/usr/bin/systemctl','daemon-reload'])
    state=show()
    if state.get('PrivateNetwork')!='yes' or state.get('DropInPaths') or APPROVAL.exists():raise ValueError('blocked state not restored')


def preflight():
    parents(Path(__file__).resolve().parent);trusted(Path(__file__).resolve(),mode=0o600)
    user=pwd.getpwnam('msp-reports')
    if (user.pw_uid,user.pw_gid)!=(995,985):raise ValueError('identity drift')
    if PUBLIC.exists():
        parents(PUBLIC)
        if (PUBLIC/'wb-883801632-E.json').exists():raise ValueError('existing E public result')
    for n,digest in ASSETS['app_files'].items():
        p=RELEASE/n;parents(p.parent);trusted(p,mode=0o644)
        if sha(p.read_bytes())!=digest:raise ValueError('accepted code drift')
    actual={p.name for p in (RELEASE/'apps/msp_marketplace_reports').glob('*.py')}
    if actual!={Path(n).name for n in ASSETS['app_files']}:raise ValueError('unknown module in accepted release')
    for n,digest in ASSETS['runtime_files'].items():
        p=RELEASE/'.venv'/n;parents(p.parent);trusted(p,mode=0o644)
        if sha(p.read_bytes())!=digest:raise ValueError('accepted runtime drift')
    for n,target in ASSETS['runtime_links'].items():
        p=RELEASE/'.venv'/n;parents(p.parent)
        if not p.is_symlink() or p.lstat().st_uid!=0 or os.readlink(p)!=target:raise ValueError('runtime link drift')
    actual_runtime={str(p.relative_to(RELEASE/'.venv')) for p in (RELEASE/'.venv').rglob('*') if p.is_file() and not p.is_symlink()}
    if actual_runtime!=set(ASSETS['runtime_files']):raise ValueError('unexpected runtime file')
    if sha(Path('/usr/bin/python3.12').read_bytes())!=ASSETS['python_sha256']:raise ValueError('host Python drift')
    trusted(UNIT,mode=0o600)
    if sha(UNIT.read_bytes())!=ASSETS['base_unit_sha256']:raise ValueError('base unit drift')
    p=RELEASE/'pilot-plan.json';trusted(p,mode=0o644)
    if sha(p.read_bytes())!=ASSETS['plan_file_sha256'] or strict_json(p.read_bytes())!=PLAN:raise ValueError('pilot plan drift')
    parents(ARCHIVE.parent);trusted(ARCHIVE,uid=995,mode=0o700)
    if (ARCHIVE/'.wb-executor/E-883801632-events.jsonl').exists():raise ValueError('preexisting E events; reconcile')
    if ARCHIVE.stat().st_gid!=985:raise ValueError('archive group drift')
    before=show()
    if before.get('ActiveState') not in ('inactive','failed') or before.get('DropInPaths') or before.get('PrivateNetwork')!='yes' or before.get('Restart')!='no':raise ValueError('pilot is active/modified')
    for base in ['/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system','/lib/systemd/system']:
        p=Path(base)/(SERVICE+'.d')
        if p.exists() or p.is_symlink():raise ValueError('unrecognized dropin directory')
    parents(CONTROL)
    if APPROVAL.exists() or APPROVAL.is_symlink():raise ValueError('existing API approval')
    trusted(REDIS_ENV,mode=0o600);redis_config(REDIS_ENV.read_bytes())
    for p in [MASTER,PILOT]:parents(p.parent);trusted(p,mode=0o600)
    master_raw=MASTER.read_bytes();pilot_raw=PILOT.read_bytes()
    credential_summary=verify_credentials(pilot_raw,master_raw,time.time())
    # Do not write credential values/hashes to receipts, GitHub or stdout.
    secret_guards=[(MASTER,sha(master_raw),MASTER.stat()),(PILOT,sha(pilot_raw),PILOT.stat()),(REDIS_ENV,sha(REDIS_ENV.read_bytes()),REDIS_ENV.stat())]
    parents(SYNTHETIC.parent);trusted(SYNTHETIC,mode=0o600)
    synth=strict_json(SYNTHETIC.read_bytes())
    if synth.get('probe_sha256')!=ASSETS['synthetic_probe_sha256']:raise ValueError('synthetic evidence origin')
    result=synth.get('result',{})
    expected={'synthetic_quota':'PASS','clients':2,'keys':4,'ttl_ceiling_seconds':715,'provider_calls':0,'live_seller_keys_touched':0,'api_enabled':False}
    if any(type(result.get(k)) is not type(v) or result[k]!=v for k,v in expected.items()):raise ValueError('synthetic acceptance evidence')
    if run(['/usr/bin/systemctl','is-active','msp-quota-redis.service']).strip()!=b'active':raise ValueError('quota service inactive')
    return secret_guards,credential_summary


def summarize():
    """Read bounded wrapper output, NEVER journalctl/header/raw HTTP payload."""
    p=STATE/'worker-output.json';trusted(p)
    if p.stat().st_size>65536:raise ValueError('worker summary oversized')
    doc=strict_json(p.read_bytes())
    return doc


def publish_result(doc):
    if not PUBLIC.exists():PUBLIC.mkdir(mode=0o755);os.chmod(PUBLIC,0o755);syncdir(PUBLIC.parent)
    parents(PUBLIC)
    write_new(PUBLIC/'wb-883801632-E.json',encoded(doc),0o644)
    write_new(STATE/'result.json',encoded(doc))
    print(json.dumps(doc,sort_keys=True))


def main():
    if os.geteuid()!=0:print('ROOT_REQUIRED;NO_CHANGES');return 2
    if sys.argv[1:] not in ([],['--hold']):raise ValueError('only fixed pilot or hold allowed')
    if STATE.exists():
        parents(STATE);trusted(STATE,mode=0o700)
        if sys.argv[1:]==['--hold']:
            trusted(STATE/'controls.json',mode=0o600)
            ownership=strict_json((STATE/'controls.json').read_bytes())
            cleanup(ownership,stop=True);print('HELD_API_BLOCKED;DATA_AND_BUDGET_PRESERVED');return 0
        if (STATE/'result.json').exists():
            trusted(STATE/'result.json',mode=0o600);print((STATE/'result.json').read_text());return 0
        raise ValueError('partial/uncertain E; no retry; inspect state or hold')
    if sys.argv[1:]:raise ValueError('no existing E to hold')
    guards,credential_summary=preflight()
    # PREPARED command is run only after independent review; owner E already granted.
    allow=resolve_allowlist()
    STATE.mkdir(mode=0o700);os.chmod(STATE,0o700);syncdir(STATE.parent)
    ownership={};started=False;cleanup_ok=False;phase='PREPARE'
    def checkpoint(name):write_new(STATE/(name+'.json'),encoded({'phase':name,'code_sha':CODE}))
    checkpoint('BEGIN')
    try:
        program_dir=Path(tempfile.mkdtemp(prefix='msp-wb-E-program-',dir='/var/lib'))
        runner=base64.b64decode(ASSETS['runner_base64'])
        if sha(runner)!=ASSETS['runner_sha256']:raise ValueError('runner integrity')
        write_new(program_dir/'runner.py',runner,0o644);os.chmod(program_dir,0o755)
        approval={'schema':1,'plan_sha256':sha(encoded(PLAN)),'code_sha256':ASSETS['app_code_sha256'],
                  'archive_root':str(ARCHIVE),'expires_epoch':int(time.time())+600,
                  'owner_api_pilot_authorized':True,'shared_quota_verified':True,'conflicting_clients_excluded':True,
                  'evidence_reference':'OWNER_ATTESTED_OLD_REMOTE_RETIRED;OWNER_APPROVED_E_883801632_MAX3;'+str(SYNTHETIC)}
        auth_raw=encoded(approval);drop_raw=dropin_text(program_dir/'runner.py',allow)
        ownership={'approval_sha256':sha(auth_raw),'dropin_sha256':sha(drop_raw),'runner_path':str(program_dir/'runner.py')}
        # Durable ownership BEFORE control mutations, for safe crash-time hold.
        write_new(STATE/'controls.json',encoded(ownership))
        DROP_DIR.mkdir(mode=0o755);os.chmod(DROP_DIR,0o755);syncdir(DROP_DIR.parent)
        write_new(DROP,drop_raw,0o644);write_new(APPROVAL,auth_raw)
        run(['/usr/bin/systemd-analyze','verify',SERVICE]);run(['/usr/bin/systemctl','daemon-reload'])
        settings=show()
        if (settings.get('PrivateNetwork')!='no' or settings.get('User')!='msp-reports' or settings.get('Group')!='msp-reports'
            or settings.get('DropInPaths')!=str(DROP) or str(REDIS_ENV) not in settings.get('EnvironmentFiles','')
            or settings.get('Restart')!='no'):raise ValueError('effective pilot configuration mismatch')
        phase='START';checkpoint('BEFORE_START');started=True
        # Exactly the installed finance unit, never an independent HTTP worker.
        child=subprocess.run(['/usr/bin/systemctl','start',SERVICE],capture_output=True,timeout=480,
                             env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
        phase='RESULT';checkpoint('SERVICE_RETURNED')
        output=summarize()
        cleanup(ownership,stop=False);cleanup_ok=True
        for p,digest,st in guards:
            now=p.stat()
            if sha(p.read_bytes())!=digest or (now.st_uid,now.st_gid,now.st_mode)!=(st.st_uid,st.st_gid,st.st_mode):raise ValueError('protected configuration changed')
        # Counts are evidence from runner + original journal, not assumed from exit0.
        complete=output.get('report_detail_complete') is True and output.get('executor',{}).get('status')=='DONE'
        status='PASS' if complete else ('PARTIAL' if output.get('executor',{}).get('status') in ('PAUSED_BUDGET','WAITING_RATE_LIMIT','WAITING_RETRY','PAGE_STAGED') else 'FAIL')
        doc={'status':status,'code_sha':CODE,'api_enabled_after_run':False,'no_schedule':True,
             'owner_old_remote_status':'OWNER_ATTESTED_OLD_REMOTE_RETIRED','credential_local_checks':credential_summary,
             'worker_exit':child.returncode,'outcome':output,'archive_root':str(ARCHIVE),
             'provider_contract':'HISTORICAL_MATCH_FIRST_AUTHORIZED_REQUEST_VALIDATES_LIVE_ACCESS',
             'protected_credentials_unchanged':True,'A_B_C':'UNCHANGED','root_state':str(STATE)}
        publish_result(doc);return 0 if status in ('PASS','PARTIAL') else 1
    except Exception as exc:
        if not cleanup_ok:
            try:cleanup(ownership,stop=started);cleanup_ok=True
            except Exception:pass
        failure={'status':'STOP_OR_UNCERTAIN','phase':phase,'error_type':type(exc).__name__,
                 'http_may_have_started':started,'api_enabled_after_run':False if cleanup_ok else None,
                 'auto_retry':False,'budget_and_pages_preserved':True,'root_state':str(STATE)}
        write_new(STATE/'failure.json',encoded(failure));print(json.dumps(failure));return 1

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'status':'STOP_OR_UNCERTAIN','error_type':type(exc).__name__,'auto_retry':False}));raise SystemExit(1)
