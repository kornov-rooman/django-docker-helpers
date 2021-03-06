import os

import pytest

from django_docker_helpers.config import ConfigLoader
from django_docker_helpers.config.backends import *
from django_docker_helpers.utils import mp_serialize_dict

REDIS_HOST = os.getenv('REDIS_HOST', '127.0.0.1')
REDIS_PORT = os.getenv('REDIS_PORT', 6379)

CONSUL_HOST = os.getenv('CONSUL_HOST', '127.0.0.1')
CONSUL_PORT = os.getenv('CONSUL_PORT', 8500)


@pytest.fixture
def store_mpt_consul_config():
    import consul
    sample = {
        'project': {
            'variable': 2
        }
    }
    c = consul.Consul(host=CONSUL_HOST, port=CONSUL_PORT)
    for path, value in mp_serialize_dict(sample, separator='/'):
        c.kv.put(path, value)
    return c


@pytest.fixture
def store_consul_config():
    import consul
    from yaml import dump
    sample = {
        'some': {
            'variable': 2,
        }
    }
    c = consul.Consul(host=CONSUL_HOST, port=CONSUL_PORT)
    data = dump(sample).encode()
    c.kv.put('my/service/config.yml', data)
    return c


@pytest.fixture
def store_mpt_redis_config():
    import redis
    sample = {
        'project': {
            'i': {
                'am': {
                    'redis': True
                }
            }
        }
    }
    c = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
    for path, value in mp_serialize_dict(sample, separator='.'):
        c.set(path, value)
        c.set('my-prefix:%s' % path, value)

    return c


@pytest.fixture
def store_redis_config():
    from redis import Redis
    from yaml import dump

    sample = {
        'some': {
            'variable': 44,
            'brutal': 666
        }
    }
    c = Redis(host=REDIS_HOST, port=REDIS_PORT)
    data = dump(sample).encode()
    c.set('my/conf/service/config.yml', data)
    return c


@pytest.fixture
def loader():
    env = {
        'PROJECT__DEBUG': 'false'
    }
    parsers = [
        EnvironmentParser(scope='project', env=env),

        MPTConsulParser(host=CONSUL_HOST, port=CONSUL_PORT, scope='project'),
        ConsulParser('my/service/config.yml', host=CONSUL_HOST, port=CONSUL_PORT),

        MPTRedisParser(host=REDIS_HOST, port=REDIS_PORT, scope='project'),
        RedisParser('my/conf/service/config.yml', host=REDIS_HOST, port=REDIS_PORT),

        YamlParser(config='./tests/data/config.yml', scope='project'),
    ]

    return ConfigLoader(parsers=parsers)


# noinspection PyMethodMayBeStatic,PyShadowingNames,PyUnusedLocal
class ConfigLoaderTest:
    def test__priority(self,
                       loader: ConfigLoader,
                       store_mpt_consul_config,
                       store_mpt_redis_config,
                       store_consul_config,
                       store_redis_config):
        assert loader.get('debug') == 'false', 'Ensure value is taken from env'
        assert loader.get('debug', coerce_type=bool) is False, 'Ensure value is coercing properly for env'

        assert loader.get('variable', coerce_type=int) == 2, 'Ensure consul MPT backend attached'
        assert loader.get('i.am.redis', coerce_type=bool) is True, 'Ensure redis MPT backend attached'

        assert loader.get('some.variable', coerce_type=int) == 2, 'Ensure consul backend attached'
        assert loader.get('some.brutal', coerce_type=int) == 666, 'Ensure redis backend attached'

    def test__availability(self, loader: ConfigLoader):
        assert loader.get('name') == 'wroom-wroom'

    def test__default(self, loader: ConfigLoader):
        sentinel = object()
        assert loader.get('nonexi', default=sentinel) is sentinel

    def test__from_env__raises_on_empty_values(self):
        with pytest.raises(ValueError):
            ConfigLoader.from_env([], {})

    def test__from_env(self):
        env = {
            'CONFIG__PARSERS': 'EnvironmentParser,RedisParser,YamlParser',
            'ENVIRONMENTPARSER__SCOPE': 'nested',
            'YAMLPARSER__CONFIG': './tests/data/config.yml',
            'REDISPARSER__HOST': 'wtf.test',
            'NESTED__VARIABLE': 'i_am_here',
        }

        loader = ConfigLoader.from_env(env=env)
        assert [type(p) for p in loader.parsers] == [EnvironmentParser, RedisParser, YamlParser]
        assert loader.get('variable') == 'i_am_here', 'Ensure env copied from ConfigLoader'

        with pytest.raises(Exception):
            loader.get('nothing.here')

        loader = ConfigLoader.from_env(env=env, silent=True)
        assert loader.get('nothing.here', True) is True

        loader = ConfigLoader.from_env(parser_modules=['EnvironmentParser'], env={})
        assert loader.parsers

    def test__import_parsers(self):
        parsers = list(ConfigLoader.import_parsers([
            'EnvironmentParser',
            'django_docker_helpers.config.backends.YamlParser'
        ]))
        assert parsers == [EnvironmentParser, YamlParser]

    def test__load_parser_options_from_env(self):
        env = {
            'REDISPARSER__ENDPOINT': 'go.deep',
            'REDISPARSER__HOST': 'my-host',
            'REDISPARSER__PORT': '66',
        }

        res = ConfigLoader.load_parser_options_from_env(RedisParser, env)
        assert res == {'endpoint': 'go.deep', 'host': 'my-host', 'port': 66}

        env = {
            'ENVIRONMENTPARSER__SCOPE': 'deep',
        }
        res = ConfigLoader.load_parser_options_from_env(EnvironmentParser, env)
        assert res == {'scope': 'deep'}

    def test__config_read_queue(self,
                                loader: ConfigLoader,
                                store_mpt_consul_config,
                                store_mpt_redis_config,
                                store_consul_config,
                                store_redis_config):
        loader.get('some.variable')
        loader.get('some.brutal')
        loader.get('debug')
        loader.get('i.am.redis')
        loader.get('variable')
        loader.get('name')
        loader.get('nothing.here', 'very long string lol')
        loader.get('secret')

        assert loader.config_read_queue
        assert '\033' in ''.join(loader.format_config_read_queue(color=True))
        assert '\033' not in ''.join(loader.format_config_read_queue(color=False))

        loader.print_config_read_queue(color=True)
